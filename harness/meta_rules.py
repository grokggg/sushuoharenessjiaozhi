"""
harness.meta_rules — 四条元协作规则引擎 (v2.0)

实现从脑科学启发抽象出的四条协作元规则。
全部为纯消息与权重管控逻辑，不包含任何生物细胞仿真代码。

四条规则：
  ① 强势信号抑制 — 检测单一观点主导度 > 阈值时注入反向质询
  ② 集群震荡检测 — 检测同一问题被推翻 > N轮 时强制回归原始观测
  ③ 冲突调解 — 多 Agent 矛盾时以 B1 增强基准过滤偏离的主观推演
  ④ 超限熔断 — 连续 > N轮 不收敛时标记证据不足，禁止强行下定论

v2.0 增强：
  - TaskProfile 任务感知自适应阈值
  - AgentCredibility 信誉分动态更新
  - 多维收敛判定（置信度 + 证据链 + 问题衰减 + 红队防御）
  - HypothesisPool 假说池集成

规则全部在 harness 层执行，子 Agent 无感知。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brain_subsystem.constants import BRAIN_CONSTANTS
from harness.structs import (
    MetaRuleRecord,
    MetaRulesDecision,
    TaskProfile,
    AgentCredibility,
    ConvergenceVector,
)


# =============================================================================
# 元规则引擎
# =============================================================================


class MetaRules:
    """
    Harness 元协作规则引擎 (v2.0)

    对收集到的全体 Agent 原始输出执行四条消息管控规则，
    决定本轮结果是收敛、需迭代还是触发熔断。

    v2.0 关键增强：
    - 通过 TaskProfile 实现任务感知阈值自适应
    - 通过 AgentCredibility 实现基于历史表现的信誉累积
    - 多维收敛判定替代单一置信度方差判定
    - 支持 HypothesisPool 假说池输入

    关键设计原则：
    - 只做消息权重管控，不做生物细胞仿真
    - 不直接修改 Agent 输出内容
    - 所有决策可追溯（通过 MetaRuleRecord）
    """

    __slots__ = (
        "_dominance_history",
        "_overturn_counts",
        "_b1_baseline",
        "_dominance_threshold",
        "_oscillation_detect_rounds",
        "_b1_deviation_threshold",
        "_max_iterations",
        "_convergence_variance",
        "_convergence_confidence",
        # v2.0
        "_task_profile",
        "_agent_credibility",
        "_prev_unresolved_count",
        "_hypothesis_pool",
    )

    def __init__(
        self,
        *,
        dominance_threshold: float = 0.60,
        oscillation_detect_rounds: int = 3,
        b1_deviation_threshold: float = 0.35,
        max_iterations: int = 5,
        convergence_variance: float = 0.15,
        convergence_confidence: float = 0.55,
        task_profile: TaskProfile | None = None,
    ) -> None:
        self._dominance_history: list[dict[str, float]] = []
        self._overturn_counts: dict[str, int] = {}
        self._b1_baseline: float | None = None

        # 任务感知 profile — 若提供则覆盖硬编码默认值
        if task_profile is not None:
            self._task_profile = task_profile
            self._dominance_threshold = task_profile.dominance_threshold
            self._oscillation_detect_rounds = task_profile.oscillation_detect_rounds
            self._b1_deviation_threshold = task_profile.b1_deviation_threshold
            self._max_iterations = task_profile.max_iterations
            self._convergence_variance = task_profile.convergence_variance
            self._convergence_confidence = task_profile.convergence_confidence
        else:
            self._task_profile = TaskProfile()
            self._dominance_threshold = dominance_threshold
            self._oscillation_detect_rounds = oscillation_detect_rounds
            self._b1_deviation_threshold = b1_deviation_threshold
            self._max_iterations = max_iterations
            self._convergence_variance = convergence_variance
            self._convergence_confidence = convergence_confidence

        # v2.0: Agent 信誉分
        self._agent_credibility: dict[str, AgentCredibility] = {}

        # v2.0: 未解决问题追踪（用于计算衰减率）
        self._prev_unresolved_count: int = 0

        # v2.0: 假说池引用（由 Orchestrator 注入）
        self._hypothesis_pool: Any = None

    # =========================================================================
    # v2.0: 外部依赖注入
    # =========================================================================

    def set_hypothesis_pool(self, pool: Any) -> None:
        """注入假说池引用，用于多维收敛判定"""
        self._hypothesis_pool = pool

    def get_agent_credibility(self, agent_id: str) -> AgentCredibility:
        """获取或创建 Agent 信誉分"""
        if agent_id not in self._agent_credibility:
            self._agent_credibility[agent_id] = AgentCredibility(agent_id=agent_id)
        return self._agent_credibility[agent_id]

    def get_all_credibility_scores(self) -> dict[str, float]:
        """获取所有 Agent 当前信誉分"""
        return {aid: c.current_score for aid, c in self._agent_credibility.items()}

    @property
    def task_profile(self) -> TaskProfile:
        return self._task_profile

    # =========================================================================
    # 主入口：评估本轮输出
    # =========================================================================

    def evaluate(
        self,
        round_outputs: dict[str, Any],
        all_outputs: dict[str, Any],
        history: list[dict[str, Any]],
        brain: Any = None,
        convergence_vector: ConvergenceVector | None = None,
    ) -> MetaRulesDecision:
        """
        对一轮 Worker 输出执行全部四条元规则

        Args:
            round_outputs:      本轮 Worker 输出 {agent_id: output}
            all_outputs:        所有历史轮次输出聚合
            history:            完整轮次历史记录
            brain:              B1 增强适配器（用于规则③冲突调解）
            convergence_vector: 外部预计算的多维收敛向量（可选）

        Returns:
            MetaRulesDecision — 包含决策和所有触发记录
        """
        logs: list[MetaRuleRecord] = []
        iteration_hints: list[str] = []
        suppressed: list[str] = []

        # 规则①: 强势信号抑制（融入 Agent 信誉分权重）
        rule1_log = self._rule_strong_signal_inhibition(round_outputs)
        if rule1_log is not None:
            logs.append(rule1_log)
            iteration_hints.append(rule1_log.action_taken)
            suppressed.extend(rule1_log.affected_agents)

        # 规则②: 集群震荡检测
        rule2_log = self._rule_cluster_oscillation(history, round_outputs)
        if rule2_log is not None:
            logs.append(rule2_log)
            iteration_hints.append(rule2_log.action_taken)
            # 更新被推翻 Agent 的信誉分
            for agent_id in round_outputs:
                cred = self.get_agent_credibility(agent_id)
                cred.update_from_round(was_overturned=True)

        # 规则③: 冲突调解（使用增强 B1 基准 + Agent 信誉分）
        rule3_log = self._rule_conflict_mediation(round_outputs, brain)
        if rule3_log is not None:
            logs.append(rule3_log)
            iteration_hints.append(rule3_log.action_taken)
            suppressed.extend(rule3_log.affected_agents)
            # 更新偏离 Agent 的信誉分
            for agent_id in rule3_log.affected_agents:
                cred = self.get_agent_credibility(agent_id)
                cred.update_from_round(b1_deviation=0.5)

        # 规则④: 超限熔断
        rule4_log = self._rule_circuit_breaker(len(history))
        if rule4_log is not None:
            logs.append(rule4_log)
            return MetaRulesDecision(
                decision="circuit_broken",
                logs=logs,
                iteration_hints=iteration_hints,
                suppressed_agents=suppressed,
            )

        # 多维收敛判定
        final_cv = convergence_vector
        if final_cv is None:
            final_cv = self._build_convergence_vector(round_outputs, history)

        if final_cv.is_converged:
            return MetaRulesDecision(
                decision="converged",
                logs=logs,
                iteration_hints=iteration_hints,
                suppressed_agents=suppressed,
                convergence_vector=final_cv,
            )

        return MetaRulesDecision(
            decision="needs_iteration",
            logs=logs,
            iteration_hints=iteration_hints,
            suppressed_agents=suppressed,
            convergence_vector=final_cv,
        )

    # =========================================================================
    # 规则①: 强势信号抑制（v2.0: 融入 Agent 信誉分权重）
    # =========================================================================

    def _rule_strong_signal_inhibition(
        self, round_outputs: dict[str, Any]
    ) -> MetaRuleRecord | None:
        """
        检测集群内单一观点是否过度垄断。

        实现：统计各 Agent 输出的"置信度"或"主导分数"，
        融入 Agent 信誉分作为权重调节因子。
        若最高分 Agent 占总权重超过阈值，注入反向质询。

        v2.0: 信誉分高的 Agent 获得更高的权重系数，
        信誉分低的 Agent 权重被降低——防止低信誉 Agent 的
        噪声输出触发误判。
        """
        if len(round_outputs) < 2:
            return None

        # 计算每个 Agent 的权重分数（融入信誉分）
        scores: dict[str, float] = {}
        for agent_id, output in round_outputs.items():
            base_score = self._extract_confidence_score(output)
            cred = self.get_agent_credibility(agent_id)
            # 信誉分调节：0.5 → 无变化，>0.5 → 放大，<0.5 → 缩小
            credibility_factor = 0.5 + cred.current_score * 0.5
            scores[agent_id] = base_score * credibility_factor

        total_score = sum(scores.values())
        if total_score == 0:
            return None

        # 检测主导度
        max_agent = max(scores, key=scores.get)  # type: ignore[arg-type]
        max_score = scores[max_agent]
        dominance = max_score / total_score

        self._dominance_history.append(scores)

        if dominance > self._dominance_threshold:
            other_agents = [a for a in scores if a != max_agent]
            return MetaRuleRecord(
                rule_id=1,
                rule_name="强势信号抑制",
                triggered_at=datetime.now(timezone.utc).isoformat(),
                trigger_reason=(
                    f"Agent {max_agent} 主导度 {dominance:.1%}，"
                    f"超过阈值 {self._dominance_threshold:.0%}"
                    f" (任务类型: {self._task_profile.uncertainty_level})"
                ),
                action_taken=(
                    f"注入反向质询：对 {max_agent} 的观点进行系统性质疑，"
                    f"要求 {other_agents} 提供反驳证据"
                ),
                affected_agents=[max_agent],
                resolution="需要下一轮引入反向质询",
            )

        return None

    # =========================================================================
    # 规则②: 集群震荡检测
    # =========================================================================

    def _rule_cluster_oscillation(
        self,
        history: list[dict[str, Any]],
        round_outputs: dict[str, Any],
    ) -> MetaRuleRecord | None:
        """
        检测多轮讨论中反复推翻重建的无效震荡模式。

        实现：追踪同一结论的推翻次数。若某个结论在过去 N 轮
        中被反复推翻且无新增证据，强制回归原始观测数据。

        这是纯模式检测：通过计数推翻次数识别震荡，不模拟振荡波形。
        """
        current_fingerprint = self._fingerprint_conclusions(round_outputs)

        overturn_count = 0
        overturned_key = ""
        for key, count in self._overturn_counts.items():
            if key in current_fingerprint:
                self._overturn_counts[key] = 0
            else:
                self._overturn_counts[key] = count + 1
                if self._overturn_counts[key] >= self._oscillation_detect_rounds:
                    overturned_key = key
                    overturn_count = self._overturn_counts[key]

        for key in current_fingerprint:
            if key not in self._overturn_counts:
                self._overturn_counts[key] = 0

        if len(history) < self._oscillation_detect_rounds:
            return None

        if overturn_count >= self._oscillation_detect_rounds:
            return MetaRuleRecord(
                rule_id=2,
                rule_name="集群震荡检测",
                triggered_at=datetime.now(timezone.utc).isoformat(),
                trigger_reason=(
                    f"结论 '{overturned_key}' 在连续 {overturn_count} 轮中"
                    f"被反复推翻，触发震荡检测"
                ),
                action_taken=(
                    "强制中断讨论链条，回归原始观测数据重新锚定。"
                    "禁止在无新增证据的情况下重复讨论该方向。"
                ),
                affected_agents=[],
                resolution="下一轮必须基于原始观测数据重新开始，不得引用被推翻的结论",
            )

        return None

    # =========================================================================
    # 规则③: 冲突调解（v2.0: 使用增强 B1 基准 + Agent 信誉分调节）
    # =========================================================================

    def _rule_conflict_mediation(
        self,
        round_outputs: dict[str, Any],
        brain: Any = None,
    ) -> MetaRuleRecord | None:
        """
        当多个 Agent 输出存在不可调和矛盾时，以 B1 增强基准进行过滤。

        v2.0 增强:
        1. 使用 BrainAdapter 的 enhanced_inference 获取差异化基准
        2. Agent 信誉分融入偏离阈值计算——高信誉 Agent 享受更宽松的阈值
        3. 如果没有增强适配器，退回到 B1 原始接口

        这不是"投票"或"编排者裁决"，而是以仿真基准为参考点。
        """
        if len(round_outputs) < 2:
            return None

        confidences: dict[str, float] = {}
        for agent_id, output in round_outputs.items():
            confidences[agent_id] = self._extract_confidence_score(output)

        if not confidences:
            return None

        values = list(confidences.values())
        conf_range = max(values) - min(values)

        # 矛盾判定：置信度跨度 > 0.4 视为存在矛盾
        if conf_range < 0.4:
            return None

        # 获取 B1 基准值（v2.0: 优先使用增强适配器）
        if brain is not None:
            try:
                # 尝试使用增强推理
                if hasattr(brain, "enhanced_inference"):
                    enhanced = brain.enhanced_inference(
                        context=f"冲突调解基准: confidences={confidences}",
                        worker_outputs=round_outputs,
                        depth=1,
                    )
                    self._b1_baseline = enhanced.get("confidence", 0.5)
                else:
                    # 退回到原始 B1 推理
                    b1_result = brain.run_inference(
                        context=f"冲突调解基准: confidences={confidences}",
                        depth=1,
                    )
                    self._b1_baseline = b1_result.get("confidence", 0.5)
            except Exception:
                self._b1_baseline = 0.5
        else:
            sorted_vals = sorted(values)
            mid = len(sorted_vals) // 2
            self._b1_baseline = sorted_vals[mid]

        # 过滤偏离基准超过阈值的输出（融入 Agent 信誉分）
        excluded: list[str] = []
        for agent_id, conf in confidences.items():
            deviation = abs(conf - self._b1_baseline)
            # 信誉分调节：高于 0.5 放宽阈值，低于 0.5 收紧阈值
            # 调节幅度被限制在 [-0.15, +0.15]，避免过度膨胀
            cred = self.get_agent_credibility(agent_id)
            tolerance_bonus = (cred.current_score - 0.5) * 0.3
            effective_threshold = self._b1_deviation_threshold + tolerance_bonus
            if deviation > effective_threshold:
                excluded.append(agent_id)

        if excluded:
            return MetaRuleRecord(
                rule_id=3,
                rule_name="冲突调解",
                triggered_at=datetime.now(timezone.utc).isoformat(),
                trigger_reason=(
                    f"Agent 置信度存在矛盾 (范围 {conf_range:.2f})，"
                    f"B1 增强基准值: {self._b1_baseline:.2f}"
                ),
                action_taken=(
                    f"以 B1 增强基准 {self._b1_baseline:.2f} 为参考，"
                    f"标记偏离超过阈值的 Agent: {excluded}。"
                    f"这些输出被标记为'过度主观推演'，不纳入下一轮。"
                ),
                affected_agents=excluded,
                resolution=f"已排除 {len(excluded)} 个偏离主观推演，保留客观输出",
            )

        return None

    # =========================================================================
    # 规则④: 超限熔断
    # =========================================================================

    def _rule_circuit_breaker(self, round_count: int) -> MetaRuleRecord | None:
        """
        当同一问题连续多轮无法收敛，标记证据不足，禁止强行下定论。

        熔断后的任务进入待补充证据队列，等待新数据注入后重新激活。
        """
        if round_count >= self._max_iterations:
            return MetaRuleRecord(
                rule_id=4,
                rule_name="超限熔断",
                triggered_at=datetime.now(timezone.utc).isoformat(),
                trigger_reason=(
                    f"已连续执行 {round_count} 轮（阈值 {self._max_iterations}），"
                    f"集群仍未收敛。任务类型: {self._task_profile.uncertainty_level}"
                ),
                action_taken=(
                    "触发熔断：标记'证据不足，无法收敛'。"
                    "禁止强行下定论。任务进入待补充证据队列。"
                    "建议人类专家介入补充新证据。"
                ),
                affected_agents=[],
                resolution="等待新的外部数据注入后重新激活该任务，或请求人类介入",
            )

        return None

    # =========================================================================
    # 多维收敛判定 (v2.0)
    # =========================================================================

    def _build_convergence_vector(
        self,
        round_outputs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> ConvergenceVector:
        """
        构建多维收敛判定向量

        维度 1: 置信度一致性（方差 + 均值）
        维度 2: 证据链完整性（从假说池获取）
        维度 3: 未解决问题衰减率
        维度 4: 红队防御力（从假说池获取）
        """
        # 维度 1: 置信度
        confidences = [
            self._extract_confidence_score(o) for o in round_outputs.values()
        ]
        if not confidences:
            return ConvergenceVector(is_converged=False)

        mean_conf = sum(confidences) / len(confidences)
        variance = (
            sum((c - mean_conf) ** 2 for c in confidences) / len(confidences)
            if len(confidences) > 1 else 0.0
        )

        # 维度 2: 证据链（从假说池获取）
        evidence_coverage = 0.5
        evidence_depth = len(history)
        if self._hypothesis_pool is not None:
            try:
                leading = self._hypothesis_pool.get_leading_hypothesis()
                if leading is not None:
                    evidence_coverage = min(1.0, (len(leading.evidence_for) + len(leading.evidence_against)) * 0.15)
            except Exception:
                pass

        # 维度 3: 未解决问题衰减
        unresolved_count = 0
        for output in round_outputs.values():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    issues = inner.get("unresolved_issues", [])
                    unresolved_count += len(issues) if isinstance(issues, list) else 0

        unresolved_decay = 0.0
        if self._prev_unresolved_count > 0:
            unresolved_decay = (self._prev_unresolved_count - unresolved_count) / max(self._prev_unresolved_count, 1)
        self._prev_unresolved_count = unresolved_count

        # 维度 4: 红队防御（从假说池获取）
        red_team_pass = 0.5
        if self._hypothesis_pool is not None:
            try:
                active = self._hypothesis_pool.get_active_hypotheses()
                if active:
                    rates = [h.red_team_pass_rate for h in active if h.red_team_tests_total > 0]
                    red_team_pass = sum(rates) / len(rates) if rates else 0.5
            except Exception:
                pass

        # 构建向量
        vector = ConvergenceVector(
            confidence_variance=variance,
            confidence_mean=mean_conf,
            evidence_chain_coverage=evidence_coverage,
            evidence_chain_depth=evidence_depth,
            unresolved_decay_rate=unresolved_decay,
            unresolved_count=unresolved_count,
            red_team_pass_rate=red_team_pass,
        )

        # 如果假说池有更精确的收敛判定，优先使用
        if self._hypothesis_pool is not None:
            try:
                pool_vector = self._hypothesis_pool.build_convergence_vector()
                if pool_vector.is_converged:
                    return pool_vector
            except Exception:
                pass

        vector.compute(
            threshold_variance=self._convergence_variance,
            threshold_confidence=self._convergence_confidence,
        )
        return vector

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _extract_confidence_score(self, output: Any) -> float:
        """从 Agent 输出中提取置信度分数"""
        if isinstance(output, dict):
            inner = output.get("output", output)
            if isinstance(inner, dict):
                conf = inner.get("confidence")
                if isinstance(conf, (int, float)):
                    return float(conf)
                assess = inner.get("overall_assessment", {})
                if isinstance(assess, dict):
                    strengths = [
                        v for k, v in assess.items()
                        if k.endswith("_evidence_strength") and isinstance(v, str)
                    ]
                    if strengths:
                        return self._strength_to_float(strengths)
            conf = output.get("confidence")
            if isinstance(conf, (int, float)):
                return float(conf)
        return 0.5

    @staticmethod
    def _strength_to_float(strengths: list[str]) -> float:
        """将证据强度等级转为数值"""
        mapping = {"A": 0.9, "B": 0.7, "C": 0.4, "D": 0.1}
        values = [mapping.get(s.upper(), 0.5) for s in strengths]
        return sum(values) / len(values) if values else 0.5

    def _fingerprint_conclusions(self, round_outputs: dict[str, Any]) -> set[str]:
        """生成本轮结论的指纹集合"""
        fingerprints: set[str] = set()
        for agent_id, output in round_outputs.items():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    for hyp in inner.get("hypotheses", []):
                        if isinstance(hyp, dict) and "hypothesis_id" in hyp:
                            fingerprints.add(hyp["hypothesis_id"])
                    for crit in inner.get("critiques", []):
                        if isinstance(crit, dict) and "critique_id" in crit:
                            fingerprints.add(crit["critique_id"])
        return fingerprints

    def _is_converged(
        self,
        round_outputs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> bool:
        """
        [兼容方法] 收敛判定 — 保留向后兼容

        v2.0 优先使用 _build_convergence_vector 的多维判定，
        此方法作为降级回退。
        """
        if len(round_outputs) < 2:
            return len(round_outputs) > 0 and len(history) >= 1

        confidences = [
            self._extract_confidence_score(o) for o in round_outputs.values()
        ]
        if not confidences:
            return False

        mean_conf = sum(confidences) / len(confidences)
        variance = sum((c - mean_conf) ** 2 for c in confidences) / len(confidences)

        if variance < self._convergence_variance and mean_conf > self._convergence_confidence:
            return True
        if variance < self._convergence_variance and len(history) >= 2:
            return True

        return False

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def b1_baseline(self) -> float | None:
        """最近一次 B1 基准值"""
        return self._b1_baseline

    @property
    def overturn_counts(self) -> dict[str, int]:
        """当前推翻计数（只读）"""
        return dict(self._overturn_counts)

    @property
    def agent_credibility(self) -> dict[str, AgentCredibility]:
        """Agent 信誉分"""
        return dict(self._agent_credibility)