"""
brain_subsystem.interface — B1-final 外部调用接口

⚠️  永久冻结 — 接口签名不可修改！
    仅允许通过定义的入参进行调用，不得暴露内部实现。
"""

from typing import Any, Optional
from brain_subsystem.constants import BrainConstants, BRAIN_CONSTANTS
from brain_subsystem.kernel import BrainKernel


class BrainInterface:
    """
    B1-final 冻结外部接口

    封装内核调用，仅暴露允许的方法签名。
    所有扩展需求应通过 harness 层适配器实现。
    """

    __slots__ = ("_kernel",)

    def __init__(self, constants: Optional[BrainConstants] = None) -> None:
        """初始化接口（仅允许传入常量池）"""
        self._kernel = BrainKernel(constants=constants)

    # --- 允许的外部调用 ---

    def run_inference(self, context: str, depth: int = 1) -> dict[str, Any]:
        """
        执行推理（允许的入参：context, depth）

        Args:
            context: 推理上下文
            depth:   推理深度

        Returns:
            推理结果
        """
        return self._kernel.infer(context=context, depth=depth)

    def merge_context(self, primary: str, secondary: str) -> dict[str, Any]:
        """
        合并上下文（允许的入参：primary, secondary）

        Args:
            primary:   主上下文
            secondary: 辅助上下文

        Returns:
            融合结果
        """
        return self._kernel.fuse_context(primary=primary, secondary=secondary)

    def compute_oscillation(self, t: float) -> float:
        """
        计算振荡值（允许的入参：t）

        Args:
            t: 时间参数

        Returns:
            振荡值
        """
        return self._kernel.oscillate(t=t)

    def is_homeostatic(self, values: list[float]) -> bool:
        """
        检测稳态（允许的入参：values）

        Args:
            values: 值序列

        Returns:
            是否稳态
        """
        return self._kernel.check_homeostasis(values=values)

    def get_kernel_state(self) -> dict[str, Any]:
        """获取内核状态快照（只读）"""
        return self._kernel.get_state()

    def reset(self) -> None:
        """重置内核状态"""
        self._kernel.reset_state()