"""
harness.orchestrator — 总调度器 (v2.0)

任务分发、收集全部 Agent 原始输出、驱动执行循环。
是整个 Harness 管控底座的核心中枢，不执行具体业务逻辑，
仅负责协调数据在各模块间的流转。

Trae Task 调度模式：
  Phase 1: build_task_descriptions() → 输出 TaskDescription 列表
  Phase 2: inject_results() → 将 Trae Task 子 Agent 返回结果注入
  Phase 3: process_results() → 安全校验 → 元规则 → 快照归档 → ReflectionOutput

v2.0 增强：
  - BrainAdapter 增强 B1 基准区分度
  - HypothesisPool 假说池多假设并行跟踪
  - TaskProfile 任务感知自适应阈值
  - Human-in-the-Loop 接口
  - 编排者轮换策略

架构铁律：
- 不做最终裁决：元规则处理由 MetaRules 模块完成
- 不直接修改 brain_subsystem：对 B1 的调用仅通过 BrainAdapter/BrainInterface
- 不包含生物启发代码：所有生物启发抽象在 MetaRules 中
- 不包含外部 LLM API 调用代码
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol

from brain_subsystem.interface import BrainInterface
from harness.brain_adapter import BrainAdapter
from harness.hypothesis_pool import HypothesisPool
from harness.structs import (
    EvidenceLink,
    MetaRuleRecord,
    MetaRulesDecision,
    ProposedTaskPayload,
    ReflectionOutput,
    TaskConstraints,
    TaskProfile,
    ConvergenceVector,
    ValidationResult,
)


# =============================================================================
# Worker 协议
# =============================================================================


class WorkerProtocol(Protocol):
    """Worker 子智能体最小接口协议"""

    @property
    def agent_id(self) -> str: ...

    async def execute(self, task_payload: dict[str, Any]) -> Any: ...


class OrchestratorProtocol(Protocol):
    """编排者最小接口协议"""

    @property
    def agent_id(self) -> str: ...

    def decompose_task(self, task: dict[str, Any]) -> list[dict[str, Any]]: ...

    def assign_worker(self, subtask: dict[str, Any]) -> str: ...

    async def execute(self, task_payload: dict[str, Any]) -> Any: ...


# =============================================================================
# 总调度器
# =============================================================================


class Orchestrator:
    """
    Harness 总调度器 — Trae Task 调度模式 (v2.0)

    职责：
    1. 接收顶层任务，驱动编排者分解
    2. 构建 TaskDescription 列表（交给 Trae Task 工具派发）
    3. 接收 Trae Task 子 Agent 返回结果
    4. 将结果送入安全校验 → 元规则 → 快照管道
    5. 管理迭代循环，生成 ReflectionOutput
    6. v2.0: 假说池管理、编排者轮换、Human-in-the-Loop
    """

    MAX_ITERATIONS: int = 5
    MAX_SUBTASKS_PER_ROUND: int = 8

    # v2.0: 编排者轮换策略
    ORCHESTRATOR_STRATEGIES = ("default", "reverse", "parallel_explore", "depth_first")

    __slots__ = (
        "_lead_researcher",
        "_workers",
        "_meta_rules",
        "_validator",
        "_snapshot_mgr",
        "_brain",
        "_brain_adapter",
        "_hypothesis_pool",
        "_round_history",
        "_iteration_count",
        "_context_version",
        "_task_counter",
        "_pending_task_descriptions",
        # v2.0
        "_task_profile",
        "_orchestrator_strategy",
        "_strategy_round",
        "_human_intervention_queue",
        "_consecutive_needs_iteration",
    )

    def __init__(
        self,
        *,
        lead_researcher: OrchestratorProtocol | None = None,
        meta_rules: Any = None,
        validator: Any = None,
        snapshot_mgr: Any = None,
        brain: BrainInterface | None = None,
        task_profile: TaskProfile | None = None,
        orchestrator_strategy: str = "default",
    ) -> None:
        self._lead_researcher = lead_researcher
        self._workers: dict[str, WorkerProtocol] = {}
        self._meta_rules = meta_rules
        self._validator = validator
        self._snapshot_mgr = snapshot_mgr

        # v2.0: 使用 BrainAdapter 包装 BrainInterface
        raw_brain = brain or BrainInterface()
        self._brain = raw_brain
        self._brain_adapter = BrainAdapter(raw_brain)

        # v2.0: 假说池
        self._hypothesis_pool = HypothesisPool()

        # v2.0: 任务感知
        self._task_profile = task_profile or TaskProfile()

        # v2.0: 编排者轮换
        self._orchestrator_strategy = orchestrator_strategy
        self._strategy_round = 0

        self._round_history: deque[dict[str, Any]] = deque(maxlen=10)
        self._iteration_count = 0
        self._context_version = ""
        self._task_counter = 0
        self._pending_task_descriptions: list[dict[str, Any]] = []

        # v2.0: Human-in-the-Loop
        self._human_intervention_queue: list[dict[str, Any]] = []
        self._consecutive_needs_iteration: int = 0

    # --- Worker 注册 ---

    def register_worker(self, worker: WorkerProtocol) -> None:
        self._workers[worker.agent_id] = worker

    def unregister_worker(self, agent_id: str) -> None:
        self._workers.pop(agent_id, None)

    @property
    def registered_workers(self) -> list[str]:
        return list(self._workers.keys())

    # =========================================================================
    # Phase 1: 构建 Task 任务描述
    # =========================================================================

    def build_task_descriptions(
        self, root_task: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        构建标准化 Task 任务描述列表，交给 Trae Task 工具派发子 Agent。

        v2.0: 自动推断 TaskProfile 并注入元规则。
        """
        task_id = root_task.get("task_id", f"task_{int(time.time())}")

        # 输入校验
        if self._validator is not None:
            val_result = self._validator.validate_root_input(root_task)
            if not val_result.is_valid:
                return [{"error": "input_validation_failed", "details": val_result.errors}]

        # v2.0: 自动推断任务画像
        self._task_profile = TaskProfile.for_task(
            task_type=root_task.get("task_type", "composite"),
            query=root_task.get("query", root_task.get("description", "")),
        )
        # 注入元规则
        if self._meta_rules is not None and hasattr(self._meta_rules, "_task_profile"):
            # 重新初始化元规则以使用任务感知阈值
            pass  # meta_rules 通过构造函数传入 task_profile

        # 生成上下文版本号
        self._context_version = self._generate_context_version()

        # 编排分解
        subtasks = self._decompose(root_task)

        # 构建 TaskDescription
        descriptions = self._build_all_descriptions(subtasks, root_task)
        self._pending_task_descriptions = descriptions
        return descriptions

    def _build_all_descriptions(
        self, subtasks: list[dict[str, Any]], root_task: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """为所有子任务构建 TaskDescription（同步方式，避免 asyncio 依赖）"""
        import asyncio

        descriptions: list[dict[str, Any]] = []

        async def _build():
            for subtask in subtasks[: self.MAX_SUBTASKS_PER_ROUND]:
                worker_id = subtask.get("assigned_worker") or self._resolve_worker(subtask)
                worker = self._workers.get(worker_id)
                if worker is None:
                    continue
                subtask["context_ref"] = self._context_version
                subtask["query"] = root_task.get("query", root_task.get("description", ""))
                try:
                    task_desc = await worker.execute(subtask)
                    descriptions.append(self._serialize_task_description(task_desc))
                except Exception as exc:
                    descriptions.append({
                        "agent_id": worker_id,
                        "task_id": subtask.get("task_id", "unknown"),
                        "error": str(exc),
                    })

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                future = concurrent.futures.Future()
                def _run():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(_build())
                        future.set_result(None)
                    finally:
                        new_loop.close()
                import threading
                t = threading.Thread(target=_run, daemon=True)
                t.start()
                t.join(timeout=10)
            else:
                loop.run_until_complete(_build())
        except RuntimeError:
            asyncio.run(_build())

        return descriptions

    def _serialize_task_description(self, task_desc: Any) -> dict[str, Any]:
        """将 TaskDescription 对象序列化为 dict"""
        if hasattr(task_desc, "__dataclass_fields__"):
            return {
                "agent_id": task_desc.agent_id,
                "agent_role": task_desc.agent_role,
                "task_id": task_desc.task_id,
                "task_type": task_desc.task_type,
                "system_prompt": task_desc.system_prompt,
                "user_message": task_desc.user_message,
                "output_format": task_desc.output_format,
                "context_ref": task_desc.context_ref,
                "metadata": task_desc.metadata if hasattr(task_desc, "metadata") else {},
            }
        return dict(task_desc) if isinstance(task_desc, dict) else {"raw": str(task_desc)}

    # =========================================================================
    # Phase 2: 注入 Trae Task 子 Agent 返回结果
    # =========================================================================

    def inject_results(self, results: dict[str, Any]) -> None:
        self._pending_results = results

    # =========================================================================
    # Phase 3: 处理结果（安全校验 → 元规则 → 快照归档 → ReflectionOutput）
    # =========================================================================

    def process_results(
        self,
        task_id: str,
        worker_results: dict[str, Any],
    ) -> ReflectionOutput:
        """
        处理 Trae Task 子 Agent 返回的结果，完成完整 Harness 管道。

        v2.0 增强:
        1. 假说池注册与证据更新
        2. 多维收敛向量构建
        3. Human-in-the-Loop 判定
        4. 编排者轮换调度
        """
        round_outputs = dict(worker_results)
        all_meta_logs: list[MetaRuleRecord] = []

        # 步骤 1: 输出校验
        if self._validator is not None:
            for agent_id, output in list(round_outputs.items()):
                val_result = self._validator.validate_output(output, agent_id)
                if not val_result.is_valid:
                    all_meta_logs.append(
                        MetaRuleRecord(
                            rule_id=0,
                            rule_name="output_validation",
                            trigger_reason=f"Agent {agent_id} 输出校验失败: {val_result.errors}",
                            action_taken="output_rejected",
                            affected_agents=[agent_id],
                        )
                    )
                    round_outputs.pop(agent_id, None)

        self._iteration_count += 1

        # 步骤 2: 记录本轮历史
        self._round_history.append({
            "round": self._iteration_count,
            "outputs": dict(round_outputs),
            "context_version": self._context_version,
        })

        # v2.0: 假说池管理
        self._hypothesis_pool.register_from_worker_outputs(
            round_outputs, round_number=self._iteration_count
        )
        self._hypothesis_pool.update_with_critiques(
            round_outputs, round_number=self._iteration_count
        )
        self._hypothesis_pool.update_statuses()

        # v2.0: 注入假说池到元规则
        if self._meta_rules is not None and hasattr(self._meta_rules, "set_hypothesis_pool"):
            self._meta_rules.set_hypothesis_pool(self._hypothesis_pool)

        # 步骤 3: 元规则处理（使用增强 B1 适配器）
        decision = MetaRulesDecision(decision="converged")
        if self._meta_rules is not None:
            decision = self._meta_rules.evaluate(
                round_outputs=round_outputs,
                all_outputs=round_outputs,
                history=list(self._round_history),
                brain=self._brain_adapter,  # v2.0: 使用增强适配器
            )
            all_meta_logs.extend(decision.logs)

        # 步骤 4: 收敛判定
        if decision.decision == "circuit_broken":
            return self._build_output(
                task_id=task_id,
                worker_outputs=round_outputs,
                meta_logs=all_meta_logs,
                status="circuit_broken",
                conclusion="证据不足，无法收敛。已触发超限熔断保护。",
                confidence=0.0,
                convergence_vector=decision.convergence_vector,
                requires_human_intervention=True,
                human_intervention_reason="超限熔断触发，集群连续多轮无法收敛。建议人类专家介入：补充新证据、调整研究方向或手动裁决。",
            )

        # v2.0: Human-in-the-Loop 判定
        requires_human = False
        human_reason = ""
        if decision.decision == "needs_iteration":
            self._consecutive_needs_iteration += 1
            if self._consecutive_needs_iteration >= 3:
                requires_human = True
                human_reason = (
                    f"集群已连续 {self._consecutive_needs_iteration} 轮无法收敛。"
                    "建议人类专家介入审查当前假说池状态和证据链。"
                )
        else:
            self._consecutive_needs_iteration = 0

        # 步骤 5: 快照归档
        snapshot_id = ""
        if self._snapshot_mgr is not None:
            # v2.0: 构建假说池快照
            hyp_snapshot = self._hypothesis_pool.snapshot()
            hyp_dict = {
                "active_count": hyp_snapshot.active_count,
                "confirmed_count": hyp_snapshot.confirmed_count,
                "falsified_count": hyp_snapshot.falsified_count,
                "hypotheses": self._hypothesis_pool.to_dict_list(),
            }
            # v2.0: 获取 Agent 信誉分
            credibility = {}
            if self._meta_rules is not None and hasattr(self._meta_rules, "get_all_credibility_scores"):
                credibility = self._meta_rules.get_all_credibility_scores()

            # v2.0: 收敛向量
            cv_dict = {
                "is_converged": decision.convergence_vector.is_converged,
                "convergence_score": decision.convergence_vector.convergence_score,
                "confidence_variance": decision.convergence_vector.confidence_variance,
                "confidence_mean": decision.convergence_vector.confidence_mean,
                "evidence_chain_coverage": decision.convergence_vector.evidence_chain_coverage,
                "unresolved_decay_rate": decision.convergence_vector.unresolved_decay_rate,
                "red_team_pass_rate": decision.convergence_vector.red_team_pass_rate,
            }

            snapshot_id = self._snapshot_mgr.archive_round(
                task_id=task_id,
                round_number=self._iteration_count,
                context_version=self._context_version,
                worker_outputs=round_outputs,
                meta_logs=[_log_to_dict(log) for log in all_meta_logs],
                convergence_vector=cv_dict,
                hypothesis_pool_snapshot=hyp_dict,
                agent_credibility=credibility,
            )

        # 步骤 6: 构建最终输出
        return self._build_output(
            task_id=task_id,
            worker_outputs=round_outputs,
            meta_logs=all_meta_logs,
            status=decision.decision,
            snapshot_id=snapshot_id,
            convergence_vector=decision.convergence_vector,
            requires_human_intervention=requires_human,
            human_intervention_reason=human_reason,
        )

    # =========================================================================
    # 兼容旧接口
    # =========================================================================

    async def run(self, root_task: dict[str, Any]) -> tuple[list[dict[str, Any]], ReflectionOutput | None]:
        descriptions = self.build_task_descriptions(root_task)
        return (descriptions, None)

    # =========================================================================
    # 编排者轮换 (v2.0)
    # =========================================================================

    def rotate_orchestrator_strategy(self) -> str:
        """
        轮换编排者策略

        每 N 轮切换一次分解策略，避免编排者系统性偏差。
        可选策略: default, reverse, parallel_explore, depth_first
        """
        self._strategy_round += 1
        if self._strategy_round % 3 == 0:
            strategies = list(self.ORCHESTRATOR_STRATEGIES)
            current_idx = strategies.index(self._orchestrator_strategy)
            self._orchestrator_strategy = strategies[(current_idx + 1) % len(strategies)]
        return self._orchestrator_strategy

    def get_orchestrator_strategy(self) -> str:
        return self._orchestrator_strategy

    # =========================================================================
    # Human-in-the-Loop (v2.0)
    # =========================================================================

    def request_human_intervention(
        self, task_id: str, reason: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        请求人类介入

        当集群连续多轮无法收敛或触发熔断时，
        打包当前状态为人类可读摘要并加入介入队列。
        """
        intervention = {
            "task_id": task_id,
            "reason": reason,
            "iteration_count": self._iteration_count,
            "consecutive_needs_iteration": self._consecutive_needs_iteration,
            "active_hypotheses": self._hypothesis_pool.to_dict_list(),
            "context": context or {},
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        self._human_intervention_queue.append(intervention)
        return intervention

    def get_pending_interventions(self) -> list[dict[str, Any]]:
        """获取所有待处理的人类介入请求"""
        return [r for r in self._human_intervention_queue if r["status"] == "pending"]

    def resolve_intervention(self, task_id: str, resolution: dict[str, Any]) -> None:
        """标记介入请求为已处理"""
        for req in self._human_intervention_queue:
            if req["task_id"] == task_id and req["status"] == "pending":
                req["status"] = "resolved"
                req["resolution"] = resolution
                req["resolved_at"] = datetime.now(timezone.utc).isoformat()

    # =========================================================================
    # 内部方法
    # =========================================================================

    def _generate_context_version(self) -> str:
        self._task_counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"ctx_{ts}_{self._task_counter}"

    def _decompose(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        if self._lead_researcher is not None:
            # v2.0: 编排者轮换 — 传递策略
            strategy = self.rotate_orchestrator_strategy()
            task["orchestrator_strategy"] = strategy
            subtasks = self._lead_researcher.decompose_task(task)
            return subtasks[: self.MAX_SUBTASKS_PER_ROUND]
        return [task]

    def _resolve_worker(self, subtask: dict[str, Any]) -> str:
        if self._lead_researcher is not None:
            return self._lead_researcher.assign_worker(subtask)
        task_type = subtask.get("task_type", "perception")
        type_map = {
            "perception": "collect_agent",
            "hypothesis_building": "hypo_builder_agent",
            "skepticism": "skeptic_agent",
            "red_team": "red_judge_agent",
            "archiving": "archive_agent",
        }
        return type_map.get(task_type, "collect_agent")

    def _build_output(
        self,
        task_id: str,
        worker_outputs: dict[str, Any],
        meta_logs: list[MetaRuleRecord],
        status: str,
        conclusion: str = "",
        confidence: float = 0.5,
        snapshot_id: str = "",
        convergence_vector: ConvergenceVector | None = None,
        requires_human_intervention: bool = False,
        human_intervention_reason: str = "",
    ) -> ReflectionOutput:
        if not conclusion:
            conclusion = self._derive_conclusion(worker_outputs, status)
        evidence = self._extract_evidence(worker_outputs)
        limitations, open_questions = self._extract_uncertainties(worker_outputs)

        # v2.0: 假说池状态
        active_hyps = self._hypothesis_pool.to_dict_list()

        # v2.0: Agent 信誉分
        credibility = {}
        if self._meta_rules is not None and hasattr(self._meta_rules, "get_all_credibility_scores"):
            credibility = self._meta_rules.get_all_credibility_scores()

        return ReflectionOutput(
            task_id=task_id,
            context_version=self._context_version,
            status=status,  # type: ignore[arg-type]
            worker_outputs=worker_outputs,
            meta_rules_log=meta_logs,
            conclusion=conclusion,
            confidence=confidence,
            evidence_chain=evidence,
            limitations=limitations,
            open_questions=open_questions,
            requires_more_data=(status != "converged"),
            created_at=datetime.now(timezone.utc).isoformat(),
            iteration_count=self._iteration_count,
            snapshot_id=snapshot_id,
            # v2.0
            convergence_vector=convergence_vector or ConvergenceVector(),
            active_hypotheses=active_hyps,
            agent_credibility=credibility,
            requires_human_intervention=requires_human_intervention,
            human_intervention_reason=human_intervention_reason,
            orchestrator_strategy=self._orchestrator_strategy,
        )

    def _derive_conclusion(self, worker_outputs: dict[str, Any], status: str) -> str:
        if status == "circuit_broken":
            return "证据不足，无法收敛。已触发超限熔断保护。"
        if not worker_outputs:
            return "无有效 Worker 输出。"
        # v2.0: 优先使用假说池领先假说
        leading = self._hypothesis_pool.get_leading_hypothesis()
        if leading and leading.posterior > 0.6:
            return f"领先假说 [{leading.hypothesis_id}]: {leading.statement[:200]} (后验: {leading.posterior:.2f})"
        agent_ids = list(worker_outputs.keys())
        return f"任务完成，共收集 {len(agent_ids)} 个 Agent 原始输出: {agent_ids}"

    def _extract_evidence(self, worker_outputs: dict[str, Any]) -> list[EvidenceLink]:
        evidence: list[EvidenceLink] = []
        for agent_id, output in worker_outputs.items():
            if isinstance(output, dict):
                inner = output.get("output", {})
                observations = inner.get("observations", [])
                for obs in observations:
                    if isinstance(obs, dict):
                        evidence.append(EvidenceLink(
                            source=agent_id,
                            content=str(obs.get("raw_content", ""))[:500],
                            timestamp=obs.get("collected_at", ""),
                            reliability=0.8,
                        ))
        return evidence

    def _extract_uncertainties(self, worker_outputs: dict[str, Any]) -> tuple[list[str], list[str]]:
        limitations: list[str] = []
        open_questions: list[str] = []
        for agent_id, output in worker_outputs.items():
            if isinstance(output, dict):
                inner = output.get("output", {})
                if isinstance(inner, dict):
                    open_questions.extend(inner.get("unresolved_issues", []))
        return limitations, open_questions

    # --- 属性 ---

    @property
    def iteration_count(self) -> int:
        return self._iteration_count

    @property
    def context_version(self) -> str:
        return self._context_version

    @property
    def round_history(self) -> list[dict[str, Any]]:
        return list(self._round_history)

    @property
    def pending_task_descriptions(self) -> list[dict[str, Any]]:
        return list(self._pending_task_descriptions)

    @property
    def hypothesis_pool(self) -> HypothesisPool:
        return self._hypothesis_pool

    @property
    def brain_adapter(self) -> BrainAdapter:
        return self._brain_adapter

    @property
    def task_profile(self) -> TaskProfile:
        return self._task_profile


def _log_to_dict(log: MetaRuleRecord) -> dict[str, Any]:
    return {
        "rule_id": log.rule_id,
        "rule_name": log.rule_name,
        "triggered_at": log.triggered_at,
        "trigger_reason": log.trigger_reason,
        "action_taken": log.action_taken,
        "affected_agents": log.affected_agents,
        "resolution": log.resolution,
    }