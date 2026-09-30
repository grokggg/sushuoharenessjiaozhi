"""
harness.hypothesis_pool — 多假设并行跟踪假说池

同时维护多个竞争假说，通过贝叶斯证据累积逐步淘汰错误假说，
而非线性收敛到单一答案。

核心机制：
  1. 假说注册：从 Worker 输出中提取假说，注册入池
  2. 证据分配：将新观测数据匹配到各假说，更新后验概率
  3. 优胜劣汰：后验概率 > 0.8 标记为 confirmed，< 0.2 标记为 falsified
  4. 红队防御：跟踪每个假说的红队测试通过率
  5. 收敛判定：当某个假说后验显著高于其他假说时，判定为收敛

设计原则：
  - 不替代元规则，作为元规则的辅助输入
  - 不直接修改 Agent 输出
  - 贝叶斯更新为近似算法，不追求数学精确
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.structs import HypothesisNode, ConvergenceVector


@dataclass
class HypothesisPoolSnapshot:
    """假说池快照（用于审计和回滚）"""
    round_number: int
    hypotheses: list[HypothesisNode] = field(default_factory=list)
    active_count: int = 0
    confirmed_count: int = 0
    falsified_count: int = 0


class HypothesisPool:
    """
    多假设并行跟踪假说池

    用法：
        pool = HypothesisPool()
        pool.register_from_worker_outputs(round_outputs, round_number=1)
        pool.update_with_evidence(evidence_list, round_number=2)
        snapshot = pool.snapshot()
    """

    __slots__ = (
        "_hypotheses",
        "_history",
        "_round_counter",
    )

    def __init__(self) -> None:
        self._hypotheses: dict[str, HypothesisNode] = {}
        self._history: list[HypothesisPoolSnapshot] = []
        self._round_counter: int = 0

    # =========================================================================
    # 假说注册
    # =========================================================================

    def register_from_worker_outputs(
        self,
        worker_outputs: dict[str, Any],
        round_number: int = 0,
    ) -> list[HypothesisNode]:
        """
        从 Worker 输出中提取假说并注册入池

        扫描 hypo_builder_agent 的输出，提取 hypotheses 列表，
        对每个假说创建 HypothesisNode 并注册。
        """
        new_nodes: list[HypothesisNode] = []
        self._round_counter = round_number

        for agent_id, output in worker_outputs.items():
            if not isinstance(output, dict):
                continue
            inner = output.get("output", output)
            if not isinstance(inner, dict):
                continue

            hypotheses = inner.get("hypotheses", [])
            if not isinstance(hypotheses, list):
                continue

            for hyp in hypotheses:
                if not isinstance(hyp, dict):
                    continue
                hyp_id = hyp.get("hypothesis_id", "")
                if not hyp_id:
                    continue

                statement = hyp.get("statement", hyp.get("description", ""))
                # 如果已存在，更新而不是重复创建
                if hyp_id in self._hypotheses:
                    existing = self._hypotheses[hyp_id]
                    existing.last_updated_round = round_number
                    continue

                node = HypothesisNode(
                    hypothesis_id=hyp_id,
                    statement=str(statement)[:500],
                    source_agent=agent_id,
                    created_round=round_number,
                    last_updated_round=round_number,
                )
                self._hypotheses[hyp_id] = node
                new_nodes.append(node)

        return new_nodes

    # =========================================================================
    # 证据更新
    # =========================================================================

    def update_with_evidence(
        self,
        evidence_list: list[dict[str, Any]],
        round_number: int = 0,
    ) -> None:
        """
        用新证据更新所有假说的后验概率

        每条证据会尝试匹配到相关假说（通过 target_hypothesis_id 字段），
        如果匹配成功则更新该假说的后验。
        """
        self._round_counter = round_number

        for evidence in evidence_list:
            target_id = evidence.get("target_hypothesis_id", "")
            supports = evidence.get("supports", True)

            if target_id and target_id in self._hypotheses:
                self._hypotheses[target_id].update_evidence(evidence, supports)

    def update_with_critiques(
        self,
        worker_outputs: dict[str, Any],
        round_number: int = 0,
    ) -> None:
        """
        从怀疑批判和红队裁判的输出中提取反对证据，
        更新对应假说。
        """
        self._round_counter = round_number

        for agent_id, output in worker_outputs.items():
            if not isinstance(output, dict):
                continue
            inner = output.get("output", output)
            if not isinstance(inner, dict):
                continue

            # 处理批判
            critiques = inner.get("critiques", [])
            if isinstance(critiques, list):
                for crit in critiques:
                    if not isinstance(crit, dict):
                        continue
                    target_id = crit.get("target_hypothesis_id", "")
                    if target_id and target_id in self._hypotheses:
                        self._hypotheses[target_id].update_evidence(
                            {"strength": crit.get("severity_score", 0.5),
                             "type": "critique",
                             "content": str(crit.get("description", ""))[:200]},
                            supports=False,
                        )

            # 处理红队测试
            red_cases = inner.get("red_team_cases", [])
            if isinstance(red_cases, list):
                for case in red_cases:
                    if not isinstance(case, dict):
                        continue
                    target_id = case.get("target_hypothesis_id", "")
                    if target_id and target_id in self._hypotheses:
                        hyp = self._hypotheses[target_id]
                        hyp.red_team_tests_total += 1
                        severity = case.get("severity", "medium")
                        # critical/high severity 的测试未通过视为强反对证据
                        if severity in ("critical", "high"):
                            hyp.update_evidence(
                                {"strength": 0.7,
                                 "type": "red_team",
                                 "severity": severity,
                                 "content": str(case.get("scenario_description", ""))[:200]},
                                supports=False,
                            )
                        else:
                            hyp.red_team_pass_count += 1
                        hyp.red_team_pass_rate = (
                            hyp.red_team_pass_count / hyp.red_team_tests_total
                            if hyp.red_team_tests_total > 0 else 0.0
                        )

    # =========================================================================
    # 假说状态管理
    # =========================================================================

    def update_statuses(self) -> None:
        """根据后验概率更新假说状态"""
        for hyp in self._hypotheses.values():
            if hyp.posterior >= 0.80:
                hyp.status = "confirmed"
            elif hyp.posterior <= 0.20:
                hyp.status = "falsified"
            elif self._round_counter - hyp.last_updated_round > 3:
                hyp.status = "stale"
            else:
                hyp.status = "active"

    # =========================================================================
    # 查询
    # =========================================================================

    def get_leading_hypothesis(self) -> HypothesisNode | None:
        """获取后验概率最高的活跃假说"""
        active = [h for h in self._hypotheses.values() if h.status == "active"]
        if not active:
            return None
        return max(active, key=lambda h: h.posterior)

    def get_active_hypotheses(self) -> list[HypothesisNode]:
        """获取所有活跃假说"""
        return [h for h in self._hypotheses.values() if h.status == "active"]

    def get_all_hypotheses(self) -> list[HypothesisNode]:
        """获取所有假说"""
        return list(self._hypotheses.values())

    def snapshot(self) -> HypothesisPoolSnapshot:
        """生成当前假说池快照"""
        active = self.get_active_hypotheses()
        confirmed = [h for h in self._hypotheses.values() if h.status == "confirmed"]
        falsified = [h for h in self._hypotheses.values() if h.status == "falsified"]

        snap = HypothesisPoolSnapshot(
            round_number=self._round_counter,
            hypotheses=[h for h in self._hypotheses.values()],
            active_count=len(active),
            confirmed_count=len(confirmed),
            falsified_count=len(falsified),
        )
        self._history.append(snap)
        return snap

    def build_convergence_vector(self) -> ConvergenceVector:
        """
        从假说池状态构建收敛向量

        如果某个假说后验概率显著高于其他假说（差距 > 0.3），
        则判定为收敛。
        """
        active = self.get_active_hypotheses()
        if not active:
            return ConvergenceVector(is_converged=False, convergence_score=0.0)

        posteriors = [h.posterior for h in active]
        mean_posterior = sum(posteriors) / len(posteriors)
        variance = sum((p - mean_posterior) ** 2 for p in posteriors) / len(posteriors) if len(posteriors) > 1 else 0.0

        # 领先假说优势
        leading = max(active, key=lambda h: h.posterior)
        runner_up = sorted(posteriors, reverse=True)[1] if len(posteriors) > 1 else 0.0
        leader_advantage = leading.posterior - runner_up

        # 红队通过率
        red_rates = [h.red_team_pass_rate for h in active if h.red_team_tests_total > 0]
        avg_red_pass = sum(red_rates) / len(red_rates) if red_rates else 0.5

        # 未解决问题衰减
        unresolved_count = len([
            h for h in self._hypotheses.values()
            if h.status == "active" and h.posterior < 0.6
        ])

        prev_active = self._history[-1].active_count if self._history else len(active)
        unresolved_decay = (
            (prev_active - len(active)) / max(prev_active, 1)
            if prev_active > 0 else 0.0
        )

        vector = ConvergenceVector(
            confidence_variance=variance,
            confidence_mean=mean_posterior,
            evidence_chain_coverage=min(1.0, len(active) * 0.2),
            evidence_chain_depth=len(self._history),
            unresolved_decay_rate=unresolved_decay,
            unresolved_count=unresolved_count,
            red_team_pass_rate=avg_red_pass,
        )

        # 领先假说优势 > 0.3 且 后验 > 0.65 视为收敛
        if leader_advantage > 0.3 and leading.posterior > 0.65:
            vector.is_converged = True
            vector.convergence_score = 0.85
        else:
            vector.compute()

        return vector

    def to_dict_list(self) -> list[dict[str, Any]]:
        """将假说池导出为 dict 列表"""
        return [
            {
                "hypothesis_id": h.hypothesis_id,
                "statement": h.statement,
                "source_agent": h.source_agent,
                "posterior": h.posterior,
                "status": h.status,
                "evidence_for_count": len(h.evidence_for),
                "evidence_against_count": len(h.evidence_against),
                "red_team_pass_rate": h.red_team_pass_rate,
                "created_round": h.created_round,
            }
            for h in self._hypotheses.values()
        ]

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def active_count(self) -> int:
        return len(self.get_active_hypotheses())

    @property
    def hypothesis_count(self) -> int:
        return len(self._hypotheses)

    @property
    def history(self) -> list[HypothesisPoolSnapshot]:
        return list(self._history)