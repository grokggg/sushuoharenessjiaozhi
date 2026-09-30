"""
module_math_b.plugins — v1.1 插件式增量增强

默认全部关闭，通过任务 JSON 配置显式开启。
严禁修改 v1.0 已验证核心源码。

可用插件：
  - sympy_bridge:       SymPy 符号计算桥接
  - lean_repl_bridge:   Lean 4 REPL 形式化验证桥接
  - stagnation_analyzer: 停滞根因分析插件
"""

__all__ = [
    "SympyBridge",
    "LeanReplBridge",
    "StagnationAnalyzer",
    "PluginRegistry",
    "PluginBase",
    "PluginStatus",
]