"""
agents.worker_red_team — WorkerRedTeam 红队裁判工作者

加载 prompts/redjudge_agent.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 TaskDescription 交给 Trae Task 子 Agent 执行。
不包含任何 LLM API 调用代码。
"""

from __future__ import annotations

from typing import Any

from agents.base_worker import BaseWorker, TaskDescription


class WorkerRedTeam(BaseWorker):
    """WorkerRedTeam — 红队裁判 Agent"""

    PROMPT_FILE = "redjudge_agent.md"
    OUTPUT_FORMAT = (
        "JSON: {agent_id, task_id, status, output: {red_team_cases: [{case_id, target_hypothesis_id, "
        "attack_type: edge_case|adversarial_input|methodology_flaw|assumption_break|extreme_condition, "
        "scenario_description, modified_input, expected_behavior, failure_criterion, actual_result: null, "
        "severity: critical|high|medium|low}], case_count, coverage_report}}"
    )
    ROLE_NAME = "红队裁判 Agent"

    __slots__ = ()

    def __init__(self, agent_id: str = "red_judge_agent", prompts_dir: str = "prompts") -> None:
        super().__init__(
            agent_id=agent_id,
            capabilities=["adversarial_testing", "edge_case_detection", "assumption_breaking", "severity_assessment"],
            prompts_dir=prompts_dir,
        )

    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        task_id = task_payload.get("task_id", "unknown")
        context_ref = task_payload.get("context_ref", "")

        user_message = self._build_user_message(task_id, task_payload)
        return self.build_task_description(
            task_id=task_id, user_message=user_message, context_ref=context_ref, task_type="red_team",
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

## 待攻击的假说

{hyp_text if hyp_text else '（无假说数据，请基于任务描述设计对抗性测试）'}

## 上一轮迭代提示

{hints_text}

## 指令

请以红队视角，针对上述假说设计至少 2 个对抗性测试用例。
覆盖不同攻击类型（edge_case, adversarial_input, assumption_break 等）。
注意：只设计测试用例，不执行。actual_result 必须为 null。输出标准 JSON 格式。"""