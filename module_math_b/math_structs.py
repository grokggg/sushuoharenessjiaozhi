"""
module_math_b.math_structs — 数学专属独立结构体

零侵入主 harness/structs.py，完全独立的数据契约。
数学任务专用结构体，不与主系统混用任何 IO 资源。

结构体清单：
  - MathProposition:    命题本体（领域/难度/迭代深度/状态）
  - MathDerivationStep: 单步推导（前提/结论/缺口标记）
  - MathCounterExample: 反例候选（定义域/失效条件）
  - MathProofSnapshot:  数学快照元数据
  - MathAgentTaskPayload: 数学专用任务载荷（动态注入用）
  - MathValidationReport: 多层校验报告
  - MathConvergenceReport: 收敛判定报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# =============================================================================
# 数学命题
# =============================================================================

@dataclass
class MathProposition:
    """
    数学命题本体

    四态严格证明判定：
      PENDING       — 待严格推导验证
      PROVEN        — 已获得严谨证明
      DISPROVEN     — 已存在有效反例
      INCONCLUSIVE  — 证据不足无法判定
    """
    proposition_id: str
    statement: str  # 命题陈述（自然语言 + 形式化混合）
    domain: Literal[
        "number_theory", "algebra", "geometry", "analysis",
        "combinatorics", "topology", "logic", "other",
    ] = "number_theory"

    difficulty: Literal["elementary", "intermediate", "advanced", "open"] = "intermediate"
    iteration_depth: int = 0
    status: Literal["PENDING", "PROVEN", "DISPROVEN", "INCONCLUSIVE"] = "PENDING"

    # 推导链
    derivation_steps: list[MathDerivationStep] = field(default_factory=list)

    # 反例
    counter_examples: list[MathCounterExample] = field(default_factory=list)

    # 审查记录
    validation_reports: list[MathValidationReport] = field(default_factory=list)

    # 元信息
    created_at: str = ""
    updated_at: str = ""
    proven_by: str = ""  # 证明者 Agent ID
    proof_chain_hash: str = ""  # 证明链哈希


# =============================================================================
# 推导步骤
# =============================================================================

@dataclass
class MathDerivationStep:
    """
    单步数学推导

    严格记录每一步的前提、结论、推导规则，
    并标记逻辑缺口（gap）以便后续审查。
    """
    step_id: str
    step_number: int
    premises: list[str] = field(default_factory=list)  # 前提列表
    conclusion: str = ""  # 本步结论
    derivation_rule: str = ""  # 使用的推导规则/定理
    justification: str = ""  # 推导理由

    # 逻辑完整性检查
    has_gap: bool = False  # 是否存在逻辑缺口
    gap_description: str = ""  # 缺口描述
    has_hidden_assumption: bool = False  # 是否存在隐性假设
    hidden_assumption: str = ""  # 隐性假设内容
    is_circular: bool = False  # 是否循环论证
    circular_reference: str = ""  # 循环引用说明

    # 校验结果
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)

    # 来源
    source_agent: str = ""
    created_at: str = ""


# =============================================================================
# 反例
# =============================================================================

@dataclass
class MathCounterExample:
    """
    反例候选

    必须满足：定义域合法、约束合规、可复现
    """
    example_id: str
    target_proposition_id: str
    value_representation: str = ""  # 反例的值表示
    domain_check: str = ""  # 定义域验证
    constraint_check: str = ""  # 约束条件验证
    is_valid: bool = False  # 是否有效反例
    invalid_reason: str = ""  # 无效原因
    is_reproducible: bool = False  # 是否可复现

    # 验证步骤
    verification_steps: list[str] = field(default_factory=list)

    source_agent: str = ""
    created_at: str = ""


# =============================================================================
# 数学快照
# =============================================================================

@dataclass
class MathProofSnapshot:
    """
    数学快照元数据

    独立存储业务数据，桥接并入主哈希链。
    每条快照标记扩展标识 MATH_B_EXT。
    """
    snapshot_id: str
    task_id: str
    round_number: int
    timestamp: str

    # 命题状态
    propositions: list[dict[str, Any]] = field(default_factory=list)

    # 证明链
    proof_chain: list[dict[str, Any]] = field(default_factory=list)

    # 校验报告
    validation_summary: dict[str, Any] = field(default_factory=dict)

    # 收敛报告
    convergence_report: dict[str, Any] = field(default_factory=dict)

    # 哈希链
    content_hash: str = ""
    prev_snapshot_hash: str = ""

    # 扩展标识
    extension_tag: str = "MATH_B_EXT"


# =============================================================================
# 数学任务载荷
# =============================================================================

@dataclass
class MathAgentTaskPayload:
    """
    数学专用任务载荷

    运行时动态拼接：原 Prompt + 本轮数学任务约束。
    任务结束模板销毁，不留驻留污染。
    """
    task_id: str
    agent_id: str
    agent_role: str  # prover / reviewer / counter_example_seeker / experimenter
    proposition_id: str
    proposition_statement: str

    # 本轮特定约束
    domain: str = "number_theory"
    difficulty: str = "intermediate"
    max_derivation_steps: int = 20
    required_rigor: Literal["strict", "standard", "exploratory"] = "strict"

    # 动态注入的数学约束文本（不修改原生 prompt）
    injected_math_context: str = ""

    # 上一轮结果
    previous_round_findings: dict[str, Any] = field(default_factory=dict)

    created_at: str = ""


# =============================================================================
# 校验报告
# =============================================================================

@dataclass
class MathValidationReport:
    """
    多层数学逻辑校验报告
    """
    report_id: str
    proposition_id: str
    round_number: int

    # 第一层：语法与一致性
    syntax_valid: bool = True
    syntax_errors: list[str] = field(default_factory=list)
    variable_domain_valid: bool = True
    symbol_consistency_valid: bool = True
    self_contradiction_found: bool = False

    # 第二层：逻辑断层
    logical_gaps: list[dict[str, str]] = field(default_factory=list)  # [{step_id, description}]
    hidden_assumptions: list[dict[str, str]] = field(default_factory=list)
    circular_reasoning_found: bool = False
    circular_details: list[str] = field(default_factory=list)
    missing_premises: list[str] = field(default_factory=list)

    # 第三层：红队对抗
    boundary_tests: list[dict[str, Any]] = field(default_factory=list)
    edge_case_results: list[dict[str, Any]] = field(default_factory=list)
    perturbation_results: list[dict[str, Any]] = field(default_factory=list)

    # 综合判定
    overall_valid: bool = False
    overall_score: float = 0.0  # 0.0 ~ 1.0
    requires_iteration: bool = True
    iteration_hints: list[str] = field(default_factory=list)

    created_at: str = ""


# =============================================================================
# 收敛报告
# =============================================================================

@dataclass
class MathConvergenceReport:
    """
    数学收敛判定报告

    数学唯一合法收敛标准：
      1. 无断层/无跳跃/无循环/无隐性假设的完整证明 → PROVEN
      2. 定义域合法/约束合规/可复现的有效反例 → DISPROVEN
      3. 连续多轮 INCONCLUSIVE，无进展熵降为 0 → 强制终止
    """
    task_id: str
    round_number: int

    # 判定结果
    is_converged: bool = False
    convergence_type: Literal["PROVEN", "DISPROVEN", "FORCED_TERMINATE", ""] = ""
    convergence_reason: str = ""

    # 证明质量
    proof_completeness: float = 0.0  # 证明完整度 [0, 1]
    proof_gap_count: int = 0
    proof_circular_count: int = 0
    proof_hidden_assumption_count: int = 0

    # 反例质量
    counter_example_valid: bool = False
    counter_example_count: int = 0

    # 停滞检测
    stagnation_rounds: int = 0  # 连续无进展轮数
    entropy_zero: bool = False  # 无进展熵降为 0

    # 禁止项标记
    forbidden_methods_used: list[str] = field(default_factory=list)

    created_at: str = ""