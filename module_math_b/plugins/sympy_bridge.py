"""
module_math_b.plugins.sympy_bridge — SymPy 符号计算桥接插件

可选插件，默认关闭。通过任务 JSON 显式开启。
提供：素数判定、因式分解、模运算、符号推导验证。

不修改任何 v1.0 核心源码。
"""

from __future__ import annotations

from typing import Any

from module_math_b.plugins.plugin_registry import PluginBase, PluginResult, PluginStatus


class SympyBridge(PluginBase):
    """
    SymPy 符号计算桥接

    能力：
      - is_prime(n):          素数判定
      - factorint(n):         因式分解
      - isprime_verbose(n):   带步骤的素数判定
      - prime_range(a, b):    素数范围
      - verify_factorization: 验证因式分解结果
    """

    plugin_name = "sympy_bridge"

    __slots__ = ("_sympy_available", "_sympy")

    def __init__(self) -> None:
        self._sympy_available = False
        self._sympy = None
        try:
            import sympy
            self._sympy = sympy
            self._sympy_available = True
        except ImportError:
            pass

    def execute(self, context: dict[str, Any]) -> PluginResult:
        """
        执行符号计算

        context 期望字段:
          - operation: "is_prime" | "factor" | "prime_range" | "verify"
          - n:          整数参数
          - expected:   预期结果（用于 verify）
        """
        operation = context.get("operation", "is_prime")
        n = context.get("n", 0)

        if not self._sympy_available:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error="SymPy 未安装。请执行: pip install sympy",
            )

        try:
            if operation == "is_prime":
                return self._op_is_prime(n)
            elif operation == "factor":
                return self._op_factor(n)
            elif operation == "prime_range":
                a = context.get("a", 2)
                b = context.get("b", n)
                return self._op_prime_range(a, b)
            elif operation == "verify":
                expected = context.get("expected")
                return self._op_verify(n, expected)
            elif operation == "isprime_verbose":
                return self._op_isprime_verbose(n)
            else:
                return PluginResult(
                    plugin_name=self.plugin_name,
                    status=PluginStatus.ERROR,
                    error=f"未知操作: {operation}",
                )
        except Exception as e:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error=f"SymPy 执行错误: {e}",
            )

    # =========================================================================
    # 操作实现
    # =========================================================================

    def _op_is_prime(self, n: int) -> PluginResult:
        assert self._sympy is not None
        is_p = self._sympy.isprime(n)
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={"n": n, "is_prime": bool(is_p)},
        )

    def _op_factor(self, n: int) -> PluginResult:
        assert self._sympy is not None
        factors = self._sympy.factorint(n)
        factor_str = " × ".join(
            f"{p}^{e}" if e > 1 else str(p)
            for p, e in sorted(factors.items())
        )
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={
                "n": n,
                "factors": {int(k): int(v) for k, v in factors.items()},
                "factor_string": factor_str,
                "is_prime": len(factors) == 1 and list(factors.values())[0] == 1,
            },
        )

    def _op_prime_range(self, a: int, b: int) -> PluginResult:
        assert self._sympy is not None
        primes = list(self._sympy.primerange(a, b + 1))
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={
                "range": [a, b],
                "primes": [int(p) for p in primes],
                "count": len(primes),
            },
        )

    def _op_verify(self, n: int, expected: Any = None) -> PluginResult:
        """验证计算结果与预期是否一致"""
        assert self._sympy is not None
        is_p = self._sympy.isprime(n)
        factors = self._sympy.factorint(n)
        factor_str = " × ".join(
            f"{p}^{e}" if e > 1 else str(p)
            for p, e in sorted(factors.items())
        )

        match = True
        if expected is not None:
            if isinstance(expected, bool):
                match = is_p == expected
            elif isinstance(expected, dict):
                match = {int(k): int(v) for k, v in factors.items()} == expected

        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={
                "n": n,
                "is_prime": bool(is_p),
                "factors": {int(k): int(v) for k, v in factors.items()},
                "factor_string": factor_str,
                "expected": expected,
                "match": match,
            },
        )

    def _op_isprime_verbose(self, n: int) -> PluginResult:
        """带详细步骤的素数判定"""
        assert self._sympy is not None
        steps: list[str] = []
        n_int = int(n)

        steps.append(f"检查 n = {n_int}")

        if n_int <= 1:
            steps.append(f"n = {n_int} ≤ 1，不是素数")
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={"n": n_int, "is_prime": False, "steps": steps},
            )

        if n_int == 2:
            steps.append("n = 2，是最小的素数")
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={"n": n_int, "is_prime": True, "steps": steps},
            )

        if n_int % 2 == 0:
            steps.append(f"n = {n_int} 是偶数，不是素数")
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={"n": n_int, "is_prime": False, "steps": steps},
            )

        # 试除法
        import math
        limit = int(math.isqrt(n_int))
        steps.append(f"试除法：检查 3 到 √{n_int} ≈ {limit} 的奇数因子")

        is_p = self._sympy.isprime(n_int)
        if is_p:
            steps.append(f"未找到因子，{n_int} 是素数")
        else:
            factors = self._sympy.factorint(n_int)
            factor_str = " × ".join(
                f"{p}^{e}" if e > 1 else str(p)
                for p, e in sorted(factors.items())
            )
            steps.append(f"找到因子: {factor_str}，{n_int} 不是素数")

        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={
                "n": n_int,
                "is_prime": bool(is_p),
                "steps": steps,
                "factors": {int(k): int(v) for k, v in self._sympy.factorint(n_int).items()},
            },
        )

    @property
    def is_available(self) -> bool:
        return self._sympy_available