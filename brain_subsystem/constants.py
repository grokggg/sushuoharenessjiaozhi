"""
brain_subsystem.constants — B1-final 冻结常量池

⚠️  永久冻结 — 禁止修改任何常量值！
    最后一次修改时间: 2026-01-01 (B1-final 冻结基线)
    冻结版本: B1-FINAL-v1.0.0
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class BrainConstants:
    """
    B1-final 冻结常量池

    包含认知阈值、振荡参数、稳态窗口等核心常量。
    所有字段均为 Final，实例化后不可修改。
    """

    # ============================================================
    # 认知阈值 (Cognitive Thresholds)
    # ============================================================
    COGNITION_THRESHOLD_MIN: Final[float] = 0.15
    COGNITION_THRESHOLD_MAX: Final[float] = 0.95
    COGNITION_THRESHOLD_DEFAULT: Final[float] = 0.50

    # ============================================================
    # 振荡参数 (Oscillation Parameters)
    # ============================================================
    OSCILLATION_FREQ_BASE: Final[float] = 1.0        # 基础振荡频率 (Hz)
    OSCILLATION_AMPLITUDE: Final[float] = 0.3         # 振荡幅度
    OSCILLATION_DAMPING: Final[float] = 0.85          # 阻尼系数 (每周期衰减)

    # ============================================================
    # 稳态窗口 (Homeostasis Window)
    # ============================================================
    HOMEOSTASIS_WINDOW_SIZE: Final[int] = 10          # 稳态滑动窗口大小
    HOMEOSTASIS_TOLERANCE: Final[float] = 0.05        # 稳态容忍偏差
    HOMEOSTASIS_RECOVERY_RATE: Final[float] = 0.1     # 稳态恢复速率

    # ============================================================
    # 推理深度 (Inference Depth)
    # ============================================================
    MAX_INFERENCE_DEPTH: Final[int] = 5               # 最大推理链深度
    MAX_CONTEXT_SIZE: Final[int] = 8192               # 最大上下文窗口 (tokens)

    # ============================================================
    # 时间参数 (Temporal Parameters)
    # ============================================================
    RESPONSE_TIMEOUT_MS: Final[int] = 30_000          # 响应超时 (ms)
    OSCILLATION_PERIOD_MS: Final[int] = 100           # 振荡周期 (ms)

    # ============================================================
    # 安全边界 (Safety Bounds)
    # ============================================================
    MAX_ACTIVE_AGENTS: Final[int] = 16                # 最大并发 Agent 数
    MAX_MESSAGE_QUEUE_SIZE: Final[int] = 1024         # 消息队列上限
    MAX_SNAPSHOT_SIZE_MB: Final[int] = 100            # 单快照最大体积 (MB)


# 全局单例常量池
BRAIN_CONSTANTS = BrainConstants()