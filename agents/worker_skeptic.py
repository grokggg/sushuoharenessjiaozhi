"""
agents.worker_skeptic — WorkerSkeptic 怀疑批判工作者

加载 prompts/skeptic_agent.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 TaskDescription 交给 Trae Task 子 Agent 执行。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskDescription


class WorkerSkeptic(BaseWorker):
    """WorkerSkeptic — 怀疑批判 Agent"""

    PROMPT_FILE = "skeptic_agent.md"
    OUTPUT_FORMAT = (
        "JSON: {agent_id, task_id, status, output: {critiques: [{critique_id, target_hypothesis_id, "
        "vulnerability_type, description, severity, suggested_fix}], overall_assessment: {evidence_strength, "
        "critical_issues_found, major_methodological_gaps}}}"
    )
    ROLE_NAME = "怀疑批判 Agent"

    __slots__ = ()

    def __init__(self, agent_id: str = "skeptic_agent", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["logic_analysis", "methodology_review", "assumption_mining", "evidence_assessment"],
            prompts_dir=prompts_dir,
        )

    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        task_id = task_payload.get("task_id", "unknown")
        context_ref = task_payload.get("context_ref", "")

        user_message = self._build_user_message(task_id, task_payload)
        return self.build_task_description(
            task_id=task_id, user_message=user_message, context_ref=context_ref, task_type="skepticism",
        )

    def _build_user_message(self, task_id: str, task_payload: dict[str, Any]) -> str:
        hypotheses = task_payload.get("input_data", task_payload).get("hypotheses", [])
        hyp_text = ""
        if hypotheses:
            for i, hyp in enumerate(hypotheses[:5]):
                hyp_text += f"\n假说 {i+1} ({hyp.get('hypothesis_id', '?')}): {hyp.get('statement', str(hyp))[:300]}"

        hints = task_payload.get("iteration_hints", [])
        hints_text = "\n".join(f"  - {h}" for h in hints) if hints else "无"

        return f"""## 任务参数

- task_id: {task_id}

## 待审查的假说

{hyp_text if hyp_text else '（无假说数据，请基于任务描述进行方法论审查）'}

## 上一轮迭代提示

{hints_text}

## 指令

请对上述假说进行系统性批判审查。检测逻辑漏洞、方法论缺陷、混淆变量、隐性假设。
输出标准 JSON 格式，包含 critiques 列表和 overall_assessment。"""