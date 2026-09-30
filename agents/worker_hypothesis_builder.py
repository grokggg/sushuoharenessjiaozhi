"""
agents.worker_hypothesis_builder — WorkerHypothesisBuilder 假说构建工作者

加载 prompts/hypo_builder_agent.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 TaskDescription 交给 Trae Task 子 Agent 执行。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskDescription


class WorkerHypothesisBuilder(BaseWorker):
    """WorkerHypothesisBuilder — 假说构建 Agent"""

    PROMPT_FILE = "hypo_builder_agent.md"
    OUTPUT_FORMAT = (
        "JSON: {agent_id, task_id, status, output: {hypotheses: [{hypothesis_id, type: causal|mechanism|correlation|prediction, "
        "statement, evidence_basis: [{observation_id, relevant_content}], falsification_condition, test_method, "
        "scope_limitation, competitor_hypothesis}], hypothesis_count, coverage_report}}"
    )
    ROLE_NAME = "假说构建 Agent"

    __slots__ = ()

    def __init__(self, agent_id: str = "hypo_builder_agent", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["hypothesis_construction", "falsifiability_design", "competing_hypotheses"],
            prompts_dir=prompts_dir,
        )

    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        task_id = task_payload.get("task_id", "unknown")
        query = task_payload.get("query", task_payload.get("description", ""))
        context_ref = task_payload.get("context_ref", "")

        user_message = self._build_user_message(task_id, query, task_payload)
        return self.build_task_description(
            task_id=task_id, user_message=user_message, context_ref=context_ref, task_type="hypothesis_building",
        )

    def _build_user_message(self, task_id: str, query: str, task_payload: dict[str, Any]) -> str:
        observations = task_payload.get("input_data", task_payload).get("observations", [])
        obs_text = ""
        if observations:
            for i, obs in enumerate(observations[:3]):
                content = obs.get("raw_content", str(obs))[:300]
                obs_text += f"\n观测 {i+1}: {content}"

        hints = task_payload.get("iteration_hints", [])
        hints_text = "\n".join(f"  - {h}" for h in hints) if hints else "无"

        return f"""## 任务参数

- task_id: {task_id}
- query: {query}
- 上下文版本: {task_payload.get('context_ref', '')}

## 可用的观测数据

{obs_text if obs_text else '（无前置观测数据，请基于 query 建构初始假说）'}

## 上一轮迭代提示

{hints_text}

## 指令

请基于上述观测数据（如有），构建至少 2 条互斥的科学假说。
每条假说必须满足：可证伪、可测试、锚定证据、明确边界。输出标准 JSON 格式。"""