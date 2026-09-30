"""
harness — Harness 协作管控底座

模块职责：
- Orchestrator（总调度器）：任务分发、收集全部 Agent 原始输出、驱动执行循环
- MetaRules（元协作规则）：四条从脑科学启发抽象出的协作元规则，纯消息权重管控
- SafetyValidator（安全校验器）：拦截非法修改 brain_subsystem 的请求，仅放行白名单参数
- SnapshotArchive（快照归档）：基于 SHA-256 哈希链的版本归档，防篡改审计追踪

生物启发抽象说明：
- 四条元规则全部实现在 meta_rules 模块，为纯工程逻辑，不包含任何生物细胞仿真代码
- 子 Agent 无需感知底层机制，所有协作管控由 harness 层统一完成
"""

from harness.structs import (
    EvidenceLink,
    MetaRuleRecord,
    MetaRulesDecision,
    ProposedRedTeamCase,
    ProposedTaskPayload,
    ReflectionOutput,
    TaskConstraints,
    ValidationResult,
)
from harness.orchestrator import Orchestrator
from harness.meta_rules import MetaRules
from harness.safety_validator import SafetyValidator
from harness.snapshot_archive import SnapshotArchive

__all__ = [
    # 核心模块
    "Orchestrator",
    "MetaRules",
    "SafetyValidator",
    "SnapshotArchive",
    # 输出结构体
    "ReflectionOutput",
    "ProposedTaskPayload",
    "ProposedRedTeamCase",
    "MetaRuleRecord",
    "EvidenceLink",
    "TaskConstraints",
    "MetaRulesDecision",
    "ValidationResult",
]