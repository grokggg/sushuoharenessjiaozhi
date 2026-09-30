"""
module_math_b.math_template_engine — 零Prompt篡改动态模板注入

唯一合法工作方式：
  1. 永不读取、永不修改、永不覆盖原生 Agent system prompt
  2. 数学任务专属单次子任务 Payload 模板
  3. 运行时动态拼接：原 Prompt + 本轮数学任务约束
  4. 任务结束模板销毁，不留驻留污染

内置 4 套顶级数学智能体模板：
  1. 证明构造模板（正向推导）
  2. 漏洞审查模板（批判推理）
  3. 反例搜寻模板（暴力证伪）
  4. 特例实验模板（数值验证）
"""

from __future__ import annotations

from typing import Any, Literal

from module_math_b.math_structs import MathAgentTaskPayload


# =============================================================================
# 模板引擎
# =============================================================================

class MathTemplateEngine:
    """
    数学任务模板引擎

    核心原则：
      - 原生 Prompt 是只读的，绝不修改
      - 数学能力通过「单次任务层模板注入」实现
      - 任务结束模板销毁，不留驻留污染
    """

    # 4 套顶级数学智能体模板
    TEMPLATES: dict[str, str] = {
        # =====================================================================
        # 模板 1: 证明构造（正向推导）
        # =====================================================================
        "prover": """
[MATH MODE — 数学证明构造模式]

你当前的任务是构造严谨的数学证明。请严格遵循以下规则：

1. **推导步骤编号**：每一步必须编号，格式为 Step N。
2. **前提声明**：明确定义所有前提、已知条件、已证引理。
3. **推导规则**：每一步必须引用具体的推导规则或定理名称。
4. **禁止跳步**：每一个推导跳转都必须有明确的逻辑依据，禁止使用「显然」「易得」等模糊表述。
5. **结论标记**：每一步结束时明确写出该步结论。
6. **缺口标注**：如果某一步无法完全确定，必须标注 [GAP] 并说明原因。

命题: {statement}
领域: {domain}
难度: {difficulty}
要求严格度: {required_rigor}

请开始构造证明：
""",

        # =====================================================================
        # 模板 2: 漏洞审查（批判推理）
        # =====================================================================
        "reviewer": """
[MATH MODE — 数学审查模式]

你当前的任务是严格审查给定的数学证明。请逐步骤检查以下问题：

1. **逻辑断层**：是否存在推导步骤之间的逻辑跳跃？是否存在未声明的中间结论？
2. **隐性假设**：推理中是否使用了未经声明的前提？
3. **循环论证**：结论或其等价形式是否在前提中出现？
4. **定义域问题**：所有变量是否在合法的定义域内？
5. **边界条件**：证明是否覆盖了所有边界情况？
6. **反例可能性**：尝试构造一个可能违反命题结论的特例。

命题: {statement}
目标: 发现并报告所有逻辑缺陷、隐性假设、循环论证和潜在反例。

请输出审查报告：
""",

        # =====================================================================
        # 模板 3: 反例搜寻（暴力证伪）
        # =====================================================================
        "counter_example_seeker": """
[MATH MODE — 反例搜寻模式]

你当前的任务是尝试构造反例以证伪给定命题。请按以下策略进行：

1. **定义域扫描**：遍历命题定义域的关键区域。
2. **边界攻击**：重点测试定义域边界、极值点、奇点。
3. **退化情况**：检查所有退化/特殊/平凡情况。
4. **小值暴力**：对自然数命题，尝试前 N 个值的暴力验证。
5. **对称性破缺**：检查命题在对称变换下是否仍然成立。

命题: {statement}
领域: {domain}

对于找到的每个候选反例，请提供：
- 反例的值表示
- 定义域验证
- 约束条件验证
- 可复现性说明

请开始搜寻反例：
""",

        # =====================================================================
        # 模板 4: 特例实验（数值验证）
        # =====================================================================
        "experimenter": """
[MATH MODE — 特例实验模式]

你当前的任务是通过具体数值实验验证命题。请按以下步骤进行：

1. **代表性样本**：选取有代表性的数值样本进行验证。
2. **边界测试**：在定义域边界附近密集采样。
3. **随机采样**：在定义域内随机采样，寻找反例模式。
4. **渐进行为**：观察大参数下的渐进趋势。
5. **统计汇总**：汇总所有验证结果，给出实验性结论。

命题: {statement}
领域: {domain}

请执行数值实验并报告结果：
""",
    }

    __slots__ = ()

    # =========================================================================
    # 模板生成
    # =========================================================================

    def generate_payload(
        self,
        task_id: str,
        agent_id: str,
        agent_role: Literal["prover", "reviewer", "counter_example_seeker", "experimenter"],
        proposition_id: str,
        proposition_statement: str,
        domain: str = "number_theory",
        difficulty: str = "intermediate",
        required_rigor: Literal["strict", "standard", "exploratory"] = "strict",
        previous_findings: dict[str, Any] | None = None,
    ) -> MathAgentTaskPayload:
        """
        生成数学任务载荷

        运行时动态拼接：原 Prompt + 本轮数学任务约束。
        不修改原生 Agent system prompt。
        """
        from datetime import datetime, timezone

        template = self.TEMPLATES.get(agent_role, self.TEMPLATES["prover"])
        injected = template.format(
            statement=proposition_statement,
            domain=domain,
            difficulty=difficulty,
            required_rigor=required_rigor,
        )

        return MathAgentTaskPayload(
            task_id=task_id,
            agent_id=agent_id,
            agent_role=agent_role,
            proposition_id=proposition_id,
            proposition_statement=proposition_statement,
            domain=domain,
            difficulty=difficulty,
            required_rigor=required_rigor,
            injected_math_context=injected,
            previous_round_findings=previous_findings or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_all_payloads(
        self,
        task_id: str,
        proposition_id: str,
        proposition_statement: str,
        domain: str = "number_theory",
        difficulty: str = "intermediate",
    ) -> list[MathAgentTaskPayload]:
        """
        为所有 4 种角色生成任务载荷

        Returns:
            [prover_payload, reviewer_payload, seeker_payload, experimenter_payload]
        """
        from datetime import datetime, timezone

        payloads: list[MathAgentTaskPayload] = []
        roles: list[tuple[str, str]] = [
            ("prover", "prover_agent"),
            ("reviewer", "reviewer_agent"),
            ("counter_example_seeker", "counter_example_seeker_agent"),
            ("experimenter", "experimenter_agent"),
        ]

        for role, agent_id in roles:
            payload = self.generate_payload(
                task_id=task_id,
                agent_id=agent_id,
                agent_role=role,  # type: ignore[arg-type]
                proposition_id=proposition_id,
                proposition_statement=proposition_statement,
                domain=domain,
                difficulty=difficulty,
            )
            payloads.append(payload)

        return payloads

    # =========================================================================
    # 模板查询
    # =========================================================================

    def get_template(self, role: str) -> str:
        """获取指定角色的模板"""
        return self.TEMPLATES.get(role, self.TEMPLATES["prover"])

    @staticmethod
    def get_injected_context(payload: MathAgentTaskPayload) -> str:
        """提取注入的数学上下文"""
        return payload.injected_math_context

    @staticmethod
    def wrap_task_description(
        original_description: str,
        payload: MathAgentTaskPayload,
    ) -> str:
        """
        将数学模板注入包装到任务描述中

        不修改原生 Prompt，仅在任务描述层附加数学上下文。

        Args:
            original_description: 原始任务描述
            payload:             数学任务载荷

        Returns:
            包装后的任务描述（原始描述 + 数学上下文）
        """
        return f"{original_description}\n\n{payload.injected_math_context}"