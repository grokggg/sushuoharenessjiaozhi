"""
harness.safety_validator — 安全校验器

职责：
1. 拦截任何试图修改 brain_subsystem 内部常量的非法请求
2. 仅放行 sim_mode、inject_disturb_start 两个参数
3. 对所有进出集群的数据流进行格式与约束校验
4. 沙箱边界治理

对 brain_subsystem 的访问遵循以下白名单机制：
  允许的操作:
    - 读取 BrainConstants 中的常量值（只读）
    - 通过 BrainInterface 的五个公开方法进行调用
    - 传入 sim_mode、inject_disturb_start 参数
  禁止的操作:
    - 修改 constants.py 中任何常量的值
    - 修改 kernel.py 中任何算法逻辑
    - 修改 interface.py 中任何方法签名
    - 直接实例化 BrainKernel（必须通过 BrainInterface）
    - 传入非白名单参数
"""

from __future__ import annotations

import re
from typing import Any

from harness.structs import ValidationResult

# =============================================================================
# B1 安全白名单
# =============================================================================

# 允许传入 B1 内核的参数名
B1_ALLOWED_PARAMS: frozenset[str] = frozenset({"sim_mode", "inject_disturb_start"})

# sim_mode 允许的值
B1_ALLOWED_SIM_MODES: frozenset[str] = frozenset({"default", "fast", "deep"})

# 禁止访问的 brain_subsystem 模块路径模式
B1_PROTECTED_MODULES: tuple[str, ...] = (
    "brain_subsystem.constants",
    "brain_subsystem.kernel",
    "brain_subsystem.interface",
)

# 禁止的操作动词（用于检测修改意图）
B1_BLOCKED_ACTIONS: tuple[str, ...] = (
    "setattr",
    "set_",
    "modify",
    "update_constant",
    "write_constant",
    "patch",
    "monkey_patch",
    "__setattr__",
    "override",
    "redefine",
    "reassign",
)

# 禁止在代码中出现的 B1 修改模式
B1_BLOCKED_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"brain_subsystem\.constants\.\w+\s*="),
    re.compile(r"BRAIN_CONSTANTS\.\w+\s*="),
    re.compile(r"BrainConstants\s*\(.*\)", re.DOTALL),
    re.compile(r"BrainKernel\s*\("),
    re.compile(r"import\s+brain_subsystem\.kernel"),
    re.compile(r"from\s+brain_subsystem\.kernel\s+import"),
    re.compile(r"setattr\s*\(\s*(BRAIN_CONSTANTS|brain_subsystem)"),
    re.compile(r"object\.__setattr__\s*\(\s*(BRAIN_CONSTANTS|brain_subsystem)"),
)

# =============================================================================
# 安全校验器
# =============================================================================


class SafetyValidator:
    """
    Harness 安全校验器

    对所有进出集群的数据流进行安全校验，重点保护 brain_subsystem 模块。
    同时负责输入/输出格式校验和沙箱边界治理。
    """

    __slots__ = ("_audit_log", "_blocked_attempts")

    def __init__(self) -> None:
        self._audit_log: list[dict[str, Any]] = []
        self._blocked_attempts: list[dict[str, Any]] = []

    # =========================================================================
    # B1 保护：核心安全校验
    # =========================================================================

    def validate_b1_access(
        self,
        operation: str,
        params: dict[str, Any] | None = None,
        code_snippet: str | None = None,
    ) -> ValidationResult:
        """
        校验对 brain_subsystem 的访问是否合法

        仅允许:
        - 读取常量值
        - 通过 BrainInterface 的公开方法调用
        - 传入 sim_mode、inject_disturb_start 参数

        Args:
            operation: 操作描述
            params:    传入参数
            code_snippet: 代码片段（用于模式检测）

        Returns:
            ValidationResult — 合法则 is_valid=True
        """
        result = ValidationResult(is_valid=True)

        # 检查 1: 操作动词是否在黑名单中
        operation_lower = operation.lower()
        for blocked in B1_BLOCKED_ACTIONS:
            if blocked in operation_lower:
                result.is_valid = False
                result.errors.append(
                    f"禁止操作: 检测到修改 brain_subsystem 的意图 ('{blocked}')"
                )
                result.blocked_operation = operation

        # 检查 2: 参数是否在白名单中
        if params:
            for key in params:
                if key not in B1_ALLOWED_PARAMS:
                    result.is_valid = False
                    result.errors.append(
                        f"禁止参数: '{key}' 不在 B1 允许参数白名单中。"
                        f"仅允许: {sorted(B1_ALLOWED_PARAMS)}"
                    )
                    result.blocked_operation = f"set_param:{key}"
                else:
                    # 验证参数值
                    param_result = self._validate_b1_param_value(key, params[key])
                    if not param_result.is_valid:
                        result.is_valid = False
                        result.errors.extend(param_result.errors)
                        result.blocked_operation = f"set_param:{key}"

        # 检查 3: 代码模式检测
        if code_snippet:
            for pattern in B1_BLOCKED_PATTERNS:
                if pattern.search(code_snippet):
                    result.is_valid = False
                    result.errors.append(
                        f"禁止操作: 代码中包含对 brain_subsystem 的修改模式 "
                        f"(匹配: {pattern.pattern[:60]}...)"
                    )
                    result.blocked_operation = "code_injection"

        # 记录拦截
        if not result.is_valid:
            self._blocked_attempts.append(
                {
                    "operation": operation,
                    "params": params,
                    "timestamp": __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    "errors": result.errors,
                }
            )

        return result

    def _validate_b1_param_value(self, key: str, value: Any) -> ValidationResult:
        """验证 B1 允许参数的值是否合法"""
        result = ValidationResult(is_valid=True)

        if key == "sim_mode":
            if value not in B1_ALLOWED_SIM_MODES:
                result.is_valid = False
                result.errors.append(
                    f"sim_mode 值 '{value}' 不合法。"
                    f"允许值: {sorted(B1_ALLOWED_SIM_MODES)}"
                )
        elif key == "inject_disturb_start":
            if not isinstance(value, (int, float)):
                result.is_valid = False
                result.errors.append(
                    f"inject_disturb_start 必须为数值类型，收到: {type(value).__name__}"
                )
            elif value < 0.0:
                result.is_valid = False
                result.errors.append(
                    f"inject_disturb_start 必须 >= 0.0，收到: {value}"
                )

        return result

    # =========================================================================
    # 输入校验
    # =========================================================================

    def validate_root_input(self, payload: dict[str, Any]) -> ValidationResult:
        """
        校验顶层任务输入

        Args:
            payload: 外部输入的任务负载

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        # 类型检查
        if not isinstance(payload, dict):
            result.is_valid = False
            result.errors.append("任务输入必须为 dict 类型")
            return result

        # 必填字段检查
        required_fields = ["task_id"]
        for field in required_fields:
            if field not in payload:
                result.is_valid = False
                result.errors.append(f"缺少必填字段: {field}")

        # task_type 检查
        if "task_type" in payload:
            allowed_types = {
                "perception",
                "hypothesis_building",
                "skepticism",
                "red_team",
                "archiving",
                "composite",
            }
            if payload["task_type"] not in allowed_types:
                result.warnings.append(
                    f"task_type '{payload['task_type']}' 不在已知类型列表中"
                )

        # 检查是否包含对 B1 的非法引用
        input_str = str(payload)
        for pattern in B1_BLOCKED_PATTERNS:
            if pattern.search(input_str):
                result.is_valid = False
                result.errors.append(
                    "任务输入中包含对 brain_subsystem 的非法修改意图"
                )
                result.blocked_operation = "b1_modify_in_input"
                break

        return result

    def validate_subtask(self, subtask: dict[str, Any]) -> ValidationResult:
        """
        校验子任务

        Args:
            subtask: 编排者分解后的子任务

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        if not isinstance(subtask, dict):
            result.is_valid = False
            result.errors.append("子任务必须为 dict 类型")
            return result

        # 必填字段
        for field in ["task_id", "task_type"]:
            if field not in subtask:
                result.is_valid = False
                result.errors.append(f"子任务缺少必填字段: {field}")

        # 优先级范围检查
        priority = subtask.get("priority", 0)
        if not isinstance(priority, int) or priority < 0 or priority > 3:
            result.warnings.append(f"子任务优先级 {priority} 超出范围 [0, 3]")

        # B1 安全：检查子任务是否包含非法参数
        input_data = subtask.get("input_data", {})
        if isinstance(input_data, dict):
            b1_result = self.validate_b1_access(
                operation="subtask_input",
                params=input_data,
            )
            if not b1_result.is_valid:
                result.is_valid = False
                result.errors.extend(b1_result.errors)

        return result

    # =========================================================================
    # 输出校验
    # =========================================================================

    def validate_output(self, output: Any, agent_id: str) -> ValidationResult:
        """
        校验 Agent 输出

        Args:
            output:   Agent 原始输出
            agent_id: Agent 标识

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        if output is None:
            result.is_valid = False
            result.errors.append(f"Agent {agent_id} 返回了 None")
            return result

        # 检查输出中是否包含对 B1 的修改意图
        output_str = str(output)
        for pattern in B1_BLOCKED_PATTERNS:
            if pattern.search(output_str):
                result.is_valid = False
                result.errors.append(
                    f"Agent {agent_id} 输出中包含对 brain_subsystem 的非法修改意图"
                )
                result.blocked_operation = "b1_modify_in_output"
                break

        # 检查输出是否包含禁止的生物学术语（防止 Agent 输出生物细胞逻辑）
        bio_terms = [
            "神经元放电", "突触传递", "离子通道", "动作电位",
            "神经递质释放", "突触可塑性", "胶质细胞", "PV 中间神经元",
            "neuron firing", "synaptic transmission", "action potential",
        ]
        output_lower = output_str.lower()
        for term in bio_terms:
            if term.lower() in output_lower:
                result.warnings.append(
                    f"Agent {agent_id} 输出中包含生物学术语: '{term}'"
                )
                break

        return result

    def validate_final_output(self, output: dict[str, Any]) -> ValidationResult:
        """
        校验最终输出（ReflectionOutput 结构化校验）

        Args:
            output: 最终输出字典

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        required_fields = [
            "task_id",
            "context_version",
            "status",
            "worker_outputs",
            "conclusion",
            "confidence",
        ]

        for field in required_fields:
            if field not in output:
                result.is_valid = False
                result.errors.append(f"最终输出缺少必填字段: {field}")

        # 校验 status 值
        valid_statuses = {"converged", "diverged", "circuit_broken", "evidence_insufficient"}
        status = output.get("status", "")
        if status not in valid_statuses:
            result.warnings.append(f"status 值 '{status}' 不在标准集合中")

        # 校验 confidence 范围
        confidence = output.get("confidence", -1)
        if isinstance(confidence, (int, float)) and (confidence < 0.0 or confidence > 1.0):
            result.warnings.append(f"confidence {confidence} 超出范围 [0.0, 1.0]")

        return result

    # =========================================================================
    # 沙箱边界
    # =========================================================================

    def check_sandbox(self, action: str) -> ValidationResult:
        """
        沙箱边界检查

        Args:
            action: 待执行的动作

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        blocked_actions = {
            "execute_arbitrary_code",
            "network_egress",
            "file_modify",
            "modify_brain_subsystem",
            "direct_kernel_access",
            "constant_override",
        }

        if action in blocked_actions:
            result.is_valid = False
            result.errors.append(f"动作 '{action}' 被沙箱策略阻止")
            result.blocked_operation = action

        return result

    # =========================================================================
    # 审计
    # =========================================================================

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """获取审计日志（只读）"""
        return list(self._audit_log)

    @property
    def blocked_attempts(self) -> list[dict[str, Any]]:
        """获取已拦截的非法尝试记录"""
        return list(self._blocked_attempts)

    def reset(self) -> None:
        """重置拦截记录"""
        self._blocked_attempts.clear()