"""
module_math_b.plugins.lean_repl_bridge — Lean 4 REPL 形式化验证桥接

可选插件，默认关闭。通过任务 JSON 显式开启。
提供：Lean 语句验证、前提检查、类型检查。

不修改任何 v1.0 核心源码。
注意：需要本地安装 Lean 4 和 lake。若未安装，优雅降级。
"""

from __future__ import annotations

import subprocess
import tempfile
import os
from typing import Any

from module_math_b.plugins.plugin_registry import PluginBase, PluginResult, PluginStatus


class LeanReplBridge(PluginBase):
    """
    Lean 4 REPL 形式化验证桥接

    能力：
      - check_statement:  验证 Lean 语句语法
      - verify_proof:     验证证明块
      - check_availability: 检测 Lean 是否可用

    若 Lean 不可用，所有操作返回 UNAVAILABLE 状态（优雅降级）。
    """

    plugin_name = "lean_repl_bridge"

    __slots__ = ("_lean_available", "_lean_path")

    def __init__(self) -> None:
        self._lean_available = False
        self._lean_path = ""
        self._detect_lean()

    def _detect_lean(self) -> None:
        """检测 Lean 4 是否可用"""
        try:
            result = subprocess.run(
                ["lean", "--version"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and "Lean" in (result.stdout + result.stderr):
                self._lean_available = True
                self._lean_path = "lean"
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 尝试 lake
        try:
            result = subprocess.run(
                ["lake", "--version"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                self._lean_available = True
                self._lean_path = "lake"
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self._lean_available = False
        self._lean_path = ""

    def execute(self, context: dict[str, Any]) -> PluginResult:
        """
        执行 Lean 验证

        context 期望字段:
          - operation: "check_statement" | "verify_proof" | "check_availability"
          - code:      Lean 代码
          - imports:   额外导入
        """
        if not self._lean_available:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.DISABLED,
                output={"lean_available": False, "message": "Lean 4 未安装或不可用"},
            )

        operation = context.get("operation", "check_availability")

        try:
            if operation == "check_availability":
                return self._op_check_availability()
            elif operation == "check_statement":
                return self._op_check_statement(context)
            elif operation == "verify_proof":
                return self._op_verify_proof(context)
            else:
                return PluginResult(
                    plugin_name=self.plugin_name,
                    status=PluginStatus.ERROR,
                    error=f"未知操作: {operation}",
                )
        except subprocess.TimeoutExpired:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.TIMEOUT,
                error="Lean 执行超时",
            )
        except Exception as e:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error=f"Lean 执行错误: {e}",
            )

    def _op_check_availability(self) -> PluginResult:
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ENABLED,
            output={
                "lean_available": self._lean_available,
                "lean_path": self._lean_path,
            },
        )

    def _op_check_statement(self, context: dict[str, Any]) -> PluginResult:
        """检查 Lean 语句语法"""
        code = context.get("code", "")
        imports = context.get("imports", "")

        full_code = f"""
import Mathlib
{imports}

{code}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False, encoding="utf-8",
        ) as f:
            f.write(full_code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [self._lean_path, "--stdin" if self._lean_path == "lean" else "build", tmp_path],
                capture_output=True, text=True, timeout=10,
                cwd=os.path.dirname(tmp_path) or ".",
            )
            errors = result.stderr.strip() if result.returncode != 0 else ""
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={
                    "valid": result.returncode == 0,
                    "exit_code": result.returncode,
                    "errors": errors[:500] if errors else "",
                    "code_length": len(code),
                },
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _op_verify_proof(self, context: dict[str, Any]) -> PluginResult:
        """验证证明块"""
        # 与 check_statement 类似，但需要完整的 theorem 结构
        statement = context.get("statement", "")
        proof = context.get("proof", "")
        imports = context.get("imports", "import Mathlib")

        full_code = f"""
{imports}

theorem auto_theorem : {statement} := by
  {proof}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", delete=False, encoding="utf-8",
        ) as f:
            f.write(full_code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [self._lean_path, tmp_path],
                capture_output=True, text=True, timeout=10,
                cwd=os.path.dirname(tmp_path) or ".",
            )
            errors = result.stderr.strip() if result.returncode != 0 else ""
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={
                    "verified": result.returncode == 0,
                    "exit_code": result.returncode,
                    "errors": errors[:500] if errors else "",
                    "statement": statement[:200],
                },
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    @property
    def is_available(self) -> bool:
        return self._lean_available