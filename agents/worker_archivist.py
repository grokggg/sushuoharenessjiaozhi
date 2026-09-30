"""
agents.worker_archivist — WorkerArchivist 记录归档工作者

加载 prompts/archive_agent.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 TaskDescription 交给 Trae Task 子 Agent 执行。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskDescription


class WorkerArchivist(BaseWorker):
    """WorkerArchivist — 记录归档 Agent"""

    PROMPT_FILE = "archive_agent.md"
    OUTPUT_FORMAT = (
        "JSON: {agent_id, task_id, status, output: {round_number, round_summary, evidence_chain: [{stage, source, "
        "content, reliability}], key_findings: [str], unresolved_issues: [str], round_confidence: float, "
        "next_round_actions: [str]}}"
    )
    ROLE_NAME = "记录归档 Agent"

    __slots__ = ()

    def __init__(self, agent_id: str = "archive_agent", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["structured_logging", "evidence_chaining", "diff_comparison", "snapshot_indexing"],
            prompts_dir=prompts_dir,
        )

    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        task_id = task_payload.get("task_id", "unknown")
        context_ref = task_payload.get("context_ref", "")
        round_number = task_payload.get("round_number", 1)

        user_message = self._build_user_message(task_id, round_number, task_payload)
        return self.build_task_description(
            task_id=task_id, user_message=user_message, context_ref=context_ref, task_type="archiving",
        )

    def _build_user_message(self, task_id: str, round_number: int, task_payload: dict[str, Any]) -> str:
        worker_outputs = task_payload.get("worker_outputs", {})
        meta_logs = task_payload.get("meta_rules_log", [])

        output_summary = ""
        for agent_id, output in worker_outputs.items():
            if isinstance(output, dict):
                status = output.get("status", "?")
                output_summary += f"\n  - {agent_id}: status={status}"

        meta_summary = ""
        for log in meta_logs[:5]:
            if isinstance(log, dict):
                meta_summary += f"\n  - 规则 {log.get('rule_id', '?')}: {log.get('rule_name', '?')}"

        return f"""## 任务参数

- task_id: {task_id}
- round_number: {round_number}
- 上下文版本: {task_payload.get('context_ref', '')}

## 本轮 Worker 输出摘要

{output_summary if output_summary else '（无 Worker 输出）'}

## 元规则触发记录

{meta_summary if meta_summary else '（无元规则触发）'}

## 指令

请生成本轮的结构化归档记录。包含轮次摘要、证据链、关键发现、未决问题。
输出标准 JSON 格式。注意：只记录不编辑，完整保留原始数据。"""