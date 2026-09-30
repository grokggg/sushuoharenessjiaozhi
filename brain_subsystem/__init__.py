"""
brain_subsystem (B1-final) — 永久冻结仿真内核

⚠️  铁律：本模块标记为永久冻结！
- 禁止修改任何内部常量与内核逻辑
- 仅允许通过外部传入的标准参数进行调用
- 所有修改必须通过 harness 层的适配器间接完成

子模块：
- constants:  冻结常量池（认知阈值、振荡参数、稳态窗口）
- kernel:     冻结内核逻辑（基础推理、上下文融合、振荡模拟）
- interface:  外部调用接口（仅允许入参，不暴露内部实现）
"""

from brain_subsystem.constants import BrainConstants
from brain_subsystem.kernel import BrainKernel
from brain_subsystem.interface import BrainInterface

__all__ = [
    "BrainConstants",
    "BrainKernel",
    "BrainInterface",
]