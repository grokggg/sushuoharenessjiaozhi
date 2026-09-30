"""
agents.lead_researcher — LeadResearcher 编排者

Orchestrator 角色：加载 prompts/lead_researcher.md 模板，
负责任务分解、子任务分配、Worker 注册管理。
不做最终裁决，全部原始输出上交 Harness。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskResult


class LeadResearcher(BaseWorker):
    """
    LeadResearcher — 集群唯一编排者 (Orchestrator)

    职责：
    1. 接收顶层任务，分解为子任务 DAG
    2. 通过 harness 调度器将子任务分配给对应 Worker
    3. 聚合 Worker 结果，不做裁决
    4. 不直接执行业务逻辑
    """

    PROMPT_FILE = "lead_researcher.md"
    ROLE_NAME = "编排者 Leader"

    __slots__ = ("_worker_registry",)

    def __init__(self, agent_id: str = "lead_researcher", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["task_decomposition", "task_assignment", "result_aggregation", "global_memory"],
            prompts_dir=prompts_dir,
        )
        self._worker_registry: dict[str, BaseWorker] = {}

    # --- Worker 管理 ---

    def register_worker(self, worker: BaseWorker) -> None:
        self._worker_registry[worker.agent_id] = worker

    def unregister_worker(self, agent_id: str) -> None:
        self._worker_registry.pop(agent_id, None)

    @property
    def worker_registry(self) -> dict[str, BaseWorker]:
        return dict(self._worker_registry)

    # --- 任务分解 ---

    def decompose_task(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        subtasks = task.get("subtasks", [])
        if subtasks:
            return subtasks
        return self._auto_decompose(task)

    def _auto_decompose(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        task_type = task.get("task_type", "composite")
        task_id = task.get("task_id", "auto_task")
        query = task.get("query", task.get("description", ""))

        if task_type == "perception":
            return [{"task_id": f"{task_id}_collect", "parent_task_id": task_id, "task_type": "perception", "description": f"采集: {query}"}]
        elif task_type == "hypothesis_building":
            return [{"task_id": f"{task_id}_hypo", "parent_task_id": task_id, "task_type": "hypothesis_building", "description": f"构建假说: {query}"}]
        else:
            return [
                {"task_id": f"{task_id}_collect", "parent_task_id": task_id, "task_type": "perception", "description": f"采集原始数据: {query}", "depends_on": [], "priority": 0},
                {"task_id": f"{task_id}_hypo", "parent_task_id": task_id, "task_type": "hypothesis_building", "description": f"构建假说: {query}", "depends_on": [f"{task_id}_collect"], "priority": 1},
                {"task_id": f"{task_id}_skeptic", "parent_task_id": task_id, "task_type": "skepticism", "description": f"批判审查: {query}", "depends_on": [f"{task_id}_hypo"], "priority": 2},
                {"task_id": f"{task_id}_redteam", "parent_task_id": task_id, "task_type": "red_team", "description": f"红队对抗测试: {query}", "depends_on": [f"{task_id}_hypo"], "priority": 2},
                {"task_id": f"{task_id}_archive", "parent_task_id": task_id, "task_type": "archiving", "description": "归档本轮结果", "depends_on": [f"{task_id}_collect", f"{task_id}_hypo", f"{task_id}_skeptic", f"{task_id}_redteam"], "priority": 3},
            ]

    # --- Worker 分配 ---

    def assign_worker(self, subtask: dict[str, Any]) -> str:
        task_type = subtask.get("task_type", "perception")
        type_map = {
            "perception": "collect_agent",
            "hypothesis_building": "hypo_builder_agent",
            "skepticism": "skeptic_agent",
            "red_team": "red_judge_agent",
            "archiving": "archive_agent",
        }
        return type_map.get(task_type, "collect_agent")

    # --- 计划更新（多轮迭代核心） ---

    def update_plan(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """
        基于上一轮结果更新科研计划，生成新一轮子任务。

        B1 仿真结果 → 编排者更新科研计划 → 输出新子任务 DAG

        Args:
            task: 包含 iteration_hints 和 previous_reflection 的更新任务

        Returns:
            新一轮子任务列表
        """
        task_id = task.get("task_id", "auto_task")
        query = task.get("query", task.get("description", ""))
        hints = task.get("iteration_hints", [])
        prev = task.get("previous_reflection", {})
        prev_round = task.get("previous_round", 0)

        # 构建迭代上下文
        context_note = ""
        if hints:
            context_note = " | ".join(str(h) for h in hints[:5])

        # 基于上一轮结果生成更聚焦的子任务
        return [
            {
                "task_id": f"{task_id}_r{prev_round+1}_collect",
                "parent_task_id": task_id,
                "task_type": "perception",
                "description": f"第{prev_round+1}轮采集: 基于上一轮发现({context_note[:100]})，补充采集新观测数据",
                "depends_on": [],
                "priority": 0,
                "iteration_hints": hints,
            },
            {
                "task_id": f"{task_id}_r{prev_round+1}_hypo",
                "parent_task_id": task_id,
                "task_type": "hypothesis_building",
                "description": f"第{prev_round+1}轮假说构建: 基于新观测更新假说，重点解决未决问题",
                "depends_on": [f"{task_id}_r{prev_round+1}_collect"],
                "priority": 1,
                "iteration_hints": hints,
                "unresolved_issues": prev.get("open_questions", []),
            },
            {
                "task_id": f"{task_id}_r{prev_round+1}_skeptic",
                "parent_task_id": task_id,
                "task_type": "skepticism",
                "description": f"第{prev_round+1}轮批判审查: 审查更新后的假说，关注上一轮发现的方法论漏洞",
                "depends_on": [f"{task_id}_r{prev_round+1}_hypo"],
                "priority": 2,
                "iteration_hints": hints,
                "previous_limitations": prev.get("limitations", []),
            },
            {
                "task_id": f"{task_id}_r{prev_round+1}_redteam",
                "parent_task_id": task_id,
                "task_type": "red_team",
                "description": f"第{prev_round+1}轮红队对抗: 针对更新后的假说设计新的对抗性测试",
                "depends_on": [f"{task_id}_r{prev_round+1}_hypo"],
                "priority": 2,
                "iteration_hints": hints,
            },
            {
                "task_id": f"{task_id}_r{prev_round+1}_archive",
                "parent_task_id": task_id,
                "task_type": "archiving",
                "description": f"第{prev_round+1}轮归档: 归档本轮完整上下文和差异对比",
                "depends_on": [
                    f"{task_id}_r{prev_round+1}_collect",
                    f"{task_id}_r{prev_round+1}_hypo",
                    f"{task_id}_r{prev_round+1}_skeptic",
                    f"{task_id}_r{prev_round+1}_redteam",
                ],
                "priority": 3,
            },
        ]

    # --- 执行（返回 TaskDescription 列表） ---

    async def execute(self, task_payload: dict[str, Any]) -> Any:
        subtasks = self.decompose_task(task_payload)
        all_outputs: dict[str, Any] = {}
        for subtask in subtasks:
            worker_id = self.assign_worker(subtask)
            worker = self._worker_registry.get(worker_id)
            if worker is None:
                all_outputs[worker_id] = {"error": f"No worker found: {worker_id}", "status": "unassigned"}
                continue
            try:
                result = await worker.execute(subtask)
                all_outputs[worker_id] = result
            except Exception as exc:
                all_outputs[worker_id] = {"error": str(exc), "status": "execution_failed"}
        return {
            "agent_id": self.agent_id,
            "task_id": task_payload.get("task_id", "unknown"),
            "subtask_count": len(subtasks),
            "worker_outputs": all_outputs,
            "status": "success",
            "note": "编排者聚合结果，不做最终裁决。以上全部原始输出上交 Harness。",
        }