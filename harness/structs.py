"""
harness.structs — 共享输出结构体定义

定义 Harness 层所有标准化输出结构体，遵循系统架构定版文档 §7 规范。
作为全项目唯一的数据契约，所有模块间通信必须使用这些结构体。

v2.0 扩展：
  - TaskProfile: 任务感知自适应阈值配置
  - HypothesisNode: 假说池节点（贝叶斯证据累积）
  - AgentCredibility: Agent 信任度动态评分
  - ConvergenceVector: 多维收敛判定向量
"""

from dataclasses import dataclass, field
from typing import Any, Literal


# =============================================================================
# 任务感知配置
# =============================================================================

@dataclass(frozen=True)
class TaskProfile:
    """
    任务特征画像 — 用于自适应校准元规则阈值

    不同任务类型需要不同的协作紧度。事实性任务允许更高主导度，
    探索性任务需要更宽松的收敛条件。
    """
    uncertainty_level: Literal["low", "medium", "high", "exploratory"] = "medium"
    dominance_threshold: float = 0.60
    oscillation_detect_rounds: int = 3
    b1_deviation_threshold: float = 0.35
    max_iterations: int = 5
    convergence_variance: float = 0.15
    convergence_confidence: float = 0.55

    @classmethod
    def for_task(cls, task_type: str, query: str = "") -> "TaskProfile":
        """根据任务类型自动推断合适的 profile"""
        if task_type in ("factual", "fact_check", "verification"):
            return cls(
                uncertainty_level="low",
                dominance_threshold=0.75,
                oscillation_detect_rounds=2,
                b1_deviation_threshold=0.20,
                max_iterations=3,
                convergence_variance=0.10,
                convergence_confidence=0.70,
            )
        elif task_type in ("exploratory", "open_research", "hypothesis_generation"):
            return cls(
                uncertainty_level="exploratory",
                dominance_threshold=0.50,
                oscillation_detect_rounds=4,
                b1_deviation_threshold=0.45,
                max_iterations=8,
                convergence_variance=0.20,
                convergence_confidence=0.45,
            )
        elif task_type in ("adversarial", "red_team", "security_audit"):
            return cls(
                uncertainty_level="high",
                dominance_threshold=0.55,
                oscillation_detect_rounds=3,
                b1_deviation_threshold=0.40,
                max_iterations=6,
                convergence_variance=0.18,
                convergence_confidence=0.50,
            )
        else:
            return cls()  # 默认 composite 类型


# =============================================================================
# 假说池
# =============================================================================

@dataclass
class HypothesisNode:
    """
    假说池中的一个竞争假说节点

    每个假说独立追踪证据强度，通过贝叶斯更新累积支持度，
    而非简单投票。
    """
    hypothesis_id: str
    statement: str
    source_agent: str  # 提出该假说的 Agent ID

    # 贝叶斯证据累积
    prior: float = 0.5  # 先验概率 P(H)
    evidence_for: list[dict[str, Any]] = field(default_factory=list)  # 支持证据
    evidence_against: list[dict[str, Any]] = field(default_factory=list)  # 反对证据
    posterior: float = 0.5  # 后验概率 P(H|E)

    # 状态
    created_round: int = 0
    last_updated_round: int = 0
    status: Literal["active", "falsified", "confirmed", "stale"] = "active"

    # 红队测试结果
    red_team_pass_rate: float = 0.0  # 通过率
    red_team_pass_count: int = 0  # 通过次数
    red_team_tests_total: int = 0

    def update_evidence(self, evidence: dict[str, Any], supports: bool) -> None:
        """用新证据更新假说后验概率（朴素贝叶斯近似）"""
        likelihood_ratio = evidence.get("strength", 0.5)
        if supports:
            self.evidence_for.append(evidence)
            # P(H|E) = P(E|H)*P(H) / P(E), 近似: posterior 向 1 移动
            self.posterior = self.posterior + (1.0 - self.posterior) * likelihood_ratio * 0.3
        else:
            self.evidence_against.append(evidence)
            # posterior 向 0 移动
            self.posterior = self.posterior * (1.0 - likelihood_ratio * 0.3)

        self.posterior = max(0.01, min(0.99, self.posterior))
        self.last_updated_round = self.created_round + len(self.evidence_for) + len(self.evidence_against)


# =============================================================================
# Agent 信任度
# =============================================================================

@dataclass
class AgentCredibility:
    """Agent 信任度动态评分 — 基于历史表现的信誉累积"""
    agent_id: str
    base_credibility: float = 0.5  # 初始信誉分

    # 历史表现
    total_rounds: int = 0
    overturned_count: int = 0  # 被推翻次数
    b1_deviation_sum: float = 0.0  # 累计偏离
    red_team_pass_count: int = 0  # 红队通过次数
    red_team_total: int = 0

    # 综合评分
    current_score: float = 0.5

    def update_from_round(
        self,
        was_overturned: bool = False,
        b1_deviation: float = 0.0,
        red_team_passed: bool | None = None,
    ) -> float:
        """基于本轮表现更新信用分"""
        self.total_rounds += 1

        # 被推翻严重扣分
        if was_overturned:
            self.overturned_count += 1
            self.current_score *= 0.7

        # B1 偏离累积扣分
        if b1_deviation > 0.3:
            self.b1_deviation_sum += b1_deviation
            penalty = min(b1_deviation * 0.5, 0.3)
            self.current_score = max(0.1, self.current_score - penalty)

        # 红队通过加分
        if red_team_passed is not None:
            self.red_team_total += 1
            if red_team_passed:
                self.red_team_pass_count += 1
                self.current_score = min(0.95, self.current_score * 1.1)

        # 长期衰减回归均值
        if self.total_rounds > 3:
            self.current_score = self.current_score * 0.9 + self.base_credibility * 0.1

        self.current_score = max(0.1, min(0.95, self.current_score))
        return self.current_score


# =============================================================================
# 多维收敛判定
# =============================================================================

@dataclass
class ConvergenceVector:
    """
    多维收敛判定向量

    单一维度（置信度方差）容易误判"对错误结论高度一致"。
    多维向量同时检查多个独立指标，只有全部通过才判定收敛。
    """
    # 维度 1: 置信度一致性
    confidence_variance: float = 0.0  # 越小越好
    confidence_mean: float = 0.0  # 越高越好

    # 维度 2: 证据链完整性
    evidence_chain_coverage: float = 0.0  # 观测→结论 的链路覆盖率
    evidence_chain_depth: int = 0  # 最长证据链深度

    # 维度 3: 未解决问题衰减
    unresolved_decay_rate: float = 0.0  # 未解决问题数量衰减率
    unresolved_count: int = 0  # 当前未解决问题数

    # 维度 4: 红队防御力
    red_team_pass_rate: float = 0.0  # 红队测试通过率
    red_team_severity_distribution: dict[str, int] = field(default_factory=dict)

    # 综合判定
    is_converged: bool = False
    convergence_score: float = 0.0  # 综合收敛分数 [0, 1]

    def compute(
        self,
        threshold_variance: float = 0.15,
        threshold_confidence: float = 0.55,
        min_rounds: int = 1,
    ) -> "ConvergenceVector":
        """计算综合收敛判定"""
        scores: list[float] = []

        # 维度 1: 置信度共识
        if self.confidence_variance < threshold_variance:
            scores.append(1.0)
        else:
            scores.append(max(0.0, 1.0 - self.confidence_variance / threshold_variance))

        if self.confidence_mean >= threshold_confidence:
            scores.append(1.0)
        else:
            scores.append(self.confidence_mean / threshold_confidence)

        # 维度 2: 证据链覆盖
        if self.evidence_chain_coverage >= 0.6:
            scores.append(1.0)
        else:
            scores.append(self.evidence_chain_coverage / 0.6)

        # 维度 3: 问题衰减
        if self.unresolved_decay_rate >= 0.3 or self.unresolved_count <= 2:
            scores.append(1.0)
        else:
            scores.append(max(0.0, self.unresolved_decay_rate / 0.3))

        # 维度 4: 红队防御
        if self.red_team_pass_rate >= 0.5:
            scores.append(1.0)
        else:
            scores.append(self.red_team_pass_rate / 0.5)

        self.convergence_score = sum(scores) / len(scores) if scores else 0.0
        # 所有维度得分 > 0.6 且综合 > 0.7 才判定收敛
        self.is_converged = (
            self.convergence_score >= 0.7
            and all(s >= 0.5 for s in scores)
            and self.confidence_variance < threshold_variance * 1.5
        )
        return self


# =============================================================================
# 核心输出结构体
# =============================================================================


@dataclass
class ReflectionOutput:
    """Harness 元规则处理后的最终输出结构体"""

    # 任务标识
    task_id: str
    context_version: str

    # 收敛状态
    status: Literal[
        "converged", "diverged", "circuit_broken",
        "evidence_insufficient", "needs_iteration",
    ]

    # 各 Agent 原始输出
    worker_outputs: dict[str, Any] = field(default_factory=dict)

    # 元规则裁决记录
    meta_rules_log: list["MetaRuleRecord"] = field(default_factory=list)

    # 最终结论
    conclusion: str = ""
    confidence: float = 0.0
    evidence_chain: list["EvidenceLink"] = field(default_factory=list)

    # 不确定性标注
    limitations: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    requires_more_data: bool = False

    # ---- v2.0 扩展 ----
    # 多维收敛
    convergence_vector: "ConvergenceVector" = field(default_factory=ConvergenceVector)
    # 假说池状态
    active_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    # Agent 信誉分
    agent_credibility: dict[str, float] = field(default_factory=dict)
    # 是否需要人类介入
    requires_human_intervention: bool = False
    human_intervention_reason: str = ""
    # 编排者策略
    orchestrator_strategy: str = "default"

    # 元信息
    created_at: str = ""
    iteration_count: int = 0
    snapshot_id: str = ""


@dataclass
class ProposedTaskPayload:
    """编排者分解后的子任务结构体"""

    task_id: str
    parent_task_id: str
    task_type: Literal[
        "perception", "hypothesis_building",
        "skepticism", "red_team", "archiving",
    ]

    description: str = ""
    context_ref: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    constraints: "TaskConstraints" = field(default_factory=lambda: TaskConstraints())
    depends_on: list[str] = field(default_factory=list)
    priority: int = 0
    created_at: str = ""
    assigned_worker: str | None = None


@dataclass
class ProposedRedTeamCase:
    """红队裁判 Agent 提出的对抗性测试用例结构体"""

    case_id: str
    target_conclusion_id: str
    attack_type: Literal[
        "edge_case", "adversarial_input", "methodology_flaw",
        "data_poisoning", "assumption_break", "extreme_condition",
    ]
    scenario_description: str = ""
    modified_input: dict[str, Any] = field(default_factory=dict)
    expected_behavior: str = ""
    failure_criterion: str = ""
    actual_result: str | None = None
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    created_by: str = ""
    created_at: str = ""


# =============================================================================
# 辅助结构体
# =============================================================================


@dataclass
class MetaRuleRecord:
    """元规则触发记录"""
    rule_id: int
    rule_name: str
    triggered_at: str = ""
    trigger_reason: str = ""
    action_taken: str = ""
    affected_agents: list[str] = field(default_factory=list)
    resolution: str = ""


@dataclass
class EvidenceLink:
    """证据链节点"""
    source: str
    content: str
    timestamp: str = ""
    reliability: float = 0.0


@dataclass
class TaskConstraints:
    """任务约束"""
    max_duration_sec: int = 300
    max_tokens: int = 10000
    required_output_format: str = "json"
    retry_count: int = 2
    sandbox_level: str = "standard"


@dataclass
class MetaRulesDecision:
    """四条元规则综合决策结果"""
    decision: Literal["converged", "needs_iteration", "circuit_broken"]
    logs: list[MetaRuleRecord] = field(default_factory=list)
    iteration_hints: list[str] = field(default_factory=list)
    suppressed_agents: list[str] = field(default_factory=list)
    # v2.0: 附加收敛向量
    convergence_vector: "ConvergenceVector" = field(default_factory=ConvergenceVector)


@dataclass
class ValidationResult:
    """安全校验结果"""
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_operation: str | None = None