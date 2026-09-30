"""
brain_subsystem.kernel — B1-final 冻结内核逻辑

⚠️  永久冻结 — 禁止修改内核逻辑！
    所有算法实现均为冻结基线，不可变更。
    如需扩展，请通过 harness 层适配器封装。
"""

from typing import Any, Optional
from brain_subsystem.constants import BRAIN_CONSTANTS, BrainConstants


class BrainKernel:
    """
    B1-final 冻结推理内核

    提供基础推理、上下文融合、振荡模拟等核心能力。
    所有方法均为冻结实现，不可覆写。
    """

    __slots__ = ("_constants", "_state")

    def __init__(self, constants: Optional[BrainConstants] = None) -> None:
        """
        初始化内核（仅允许传入常量池实例）

        Args:
            constants: 可选的自定义常量池，默认使用全局 BRAIN_CONSTANTS
        """
        self._constants = constants or BRAIN_CONSTANTS
        self._state: dict[str, Any] = {}

    # --- 基础推理 ---

    def infer(self, context: str, depth: int = 1) -> dict[str, Any]:
        """
        基础推理：基于上下文执行推理链

        Args:
            context: 输入上下文
            depth:  推理深度（不得超过 MAX_INFERENCE_DEPTH）

        Returns:
            推理结果字典
        """
        if depth > self._constants.MAX_INFERENCE_DEPTH:
            depth = self._constants.MAX_INFERENCE_DEPTH

        # 冻结推理逻辑
        result = {
            "context": context,
            "depth": depth,
            "confidence": self._constants.COGNITION_THRESHOLD_DEFAULT,
            "inference": f"[B1-final] 推理完成: depth={depth}",
        }
        self._state["last_inference"] = result
        return result

    # --- 上下文融合 ---

    def fuse_context(self, primary: str, secondary: str) -> dict[str, Any]:
        """
        上下文融合：将辅助上下文合并到主上下文

        Args:
            primary:   主上下文
            secondary: 辅助上下文

        Returns:
            融合结果字典
        """
        fused = f"{primary}\n[FUSED]\n{secondary}"
        return {
            "fused_context": fused,
            "confidence": self._constants.COGNITION_THRESHOLD_DEFAULT,
        }

    # --- 振荡模拟 ---

    def oscillate(self, t: float) -> float:
        """
        振荡模拟：计算给定时间点的振荡值

        Args:
            t: 时间参数

        Returns:
            振荡值 (0.0 ~ 1.0)
        """
        import math

        const = self._constants
        raw = (
            const.OSCILLATION_AMPLITUDE
            * math.sin(2 * math.pi * const.OSCILLATION_FREQ_BASE * t)
            * (const.OSCILLATION_DAMPING ** t)
        )
        return max(0.0, min(1.0, raw + 0.5))

    # --- 稳态检测 ---

    def check_homeostasis(self, values: list[float]) -> bool:
        """
        稳态检测：检查值序列是否处于稳态

        Args:
            values: 最近 N 个值

        Returns:
            是否处于稳态
        """
        const = self._constants
        if len(values) < const.HOMEOSTASIS_WINDOW_SIZE:
            return False

        window = values[-const.HOMEOSTASIS_WINDOW_SIZE :]
        mean_val = sum(window) / len(window)
        deviations = [abs(v - mean_val) for v in window]
        avg_deviation = sum(deviations) / len(deviations)

        return avg_deviation <= const.HOMEOSTASIS_TOLERANCE

    # --- 状态查询 ---

    def get_state(self) -> dict[str, Any]:
        """获取内核当前状态（只读）"""
        return dict(self._state)

    def reset_state(self) -> None:
        """重置内核状态"""
        self._state.clear()