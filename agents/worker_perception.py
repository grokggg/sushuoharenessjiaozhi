"""
agents.worker_perception — WorkerPerception 采集感知工作者

加载 prompts/collect_agent.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 TaskDescription 交给 Trae Task 子 Agent 执行。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskDescription


class WorkerPerception(BaseWorker):
    """
    WorkerPerception — 采集感知 Agent

    能力：数据采集、原始观测记录、初步清洗
    输出 TaskDescription → Trae Task 子 Agent 执行
    """

    PROMPT_FILE = "collect_agent.md"
    OUTPUT_FORMAT = (
        "JSON: {agent_id, task_id, context_ref, status, output: {observations: [{observation_id, "
        "source_url, source_type, raw_content, extracted_data_points, collected_at, freshness, "
        "missing_fields, language}], observation_count, coverage_report: {sources_queried, "
        "total_results, collected_count, truncated}}, errors: [], metadata: {prompt_template, producer}}"
    )
    ROLE_NAME = "采集感知 Agent"

    __slots__ = ()

    def __init__(self, agent_id: str = "collect_agent", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["data_collection", "raw_observation", "data_cleaning", "source_tracking"],
            prompts_dir=prompts_dir,
        )

    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        task_id = task_payload.get("task_id", "unknown")
        query = task_payload.get("query", task_payload.get("description", ""))
        context_ref = task_payload.get("context_ref", "")

        user_message = self._build_user_message(task_id, query, task_payload)
        return self.build_task_description(
            task_id=task_id,
            user_message=user_message,
            context_ref=context_ref,
            task_type="perception",
        )

    def _build_user_message(self, task_id: str, query: str, task_payload: dict[str, Any]) -> str:
        hints = task_payload.get("iteration_hints", [])
        hints_text = "\n".join(f"  - {h}" for h in hints) if hints else "无"

        return f"""## 任务参数

- task_id: {task_id}
- query: {query}
- 采集范围: {task_payload.get('scope', '学术论文、技术博客')}
- 最大采集数: {task_payload.get('max_observations', 5)}
- 语言偏好: {task_payload.get('language', 'zh/en')}

## 上一轮迭代提示

{hints_text}

## 指令

请根据上述任务参数，执行数据采集。输出标准 JSON 格式的观测数据。
注意：你只能输出观测到的原始数据，不能做任何推论或解释。"""