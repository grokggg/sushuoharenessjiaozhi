"""
agents.base_worker — 工作者子智能体基类

所有 Worker 子智能体的抽象基类。
职责：读取 prompts/*.md 模板，组装子任务入参 + 角色 prompt，
输出标准化 Task 任务描述交给 Trae 运行时调度子 Agent。

约束：
- 不包含任何生物启发逻辑（PV/胶质等）
- 不包含任何外部 LLM API 调用代码
- 不直接操作调度器或元规则
- 通过 harness 提供的标准接口通信
- 只产出任务描述，不做推理
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TaskResult:
    """任务执行结果"""
    agent_id: str
    task_id: str
    status: str                    # success / failure / partial
    output: Any
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDescription:
    """
    标准化 Task 任务描述 — 交给 Trae Task 子 Agent 执行

    这是 Worker 的产出物：一个包含完整角色 prompt 和任务上下文的
    任务描述，Trae 运行时将以此为输入派发 Task 子 Agent。
    """
    agent_id: str                            # 目标 Agent ID
    agent_role: str                          # 角色名称（如 "采集感知 Agent"）
    task_id: str                             # 子任务 ID
    task_type: str                           # 任务类型
    system_prompt: str                       # 角色 prompt 模板（来自 prompts/*.md）
    user_message: str                        # 任务上下文 + 用户指令
    output_format: str                       # 期望输出格式说明
    context_ref: str = ""                    # 上下文版本号
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseWorker(ABC):
    """
    工作者子智能体基类

    约束：
    - 不包含任何生物启发逻辑
    - 不直接操作调度器或元规则
    - 通过 harness 提供的标准接口通信
    - 不包含 LLM API 调用代码
    """

    __slots__ = ("_agent_id", "_capabilities", "_prompt_template")

    # 子类覆盖：prompt 模板文件名（相对于 prompts/ 目录）
    PROMPT_FILE: str = ""

    # 子类覆盖：期望的输出格式说明
    OUTPUT_FORMAT: str = "标准 JSON 格式"

    # 子类覆盖：角色名称
    ROLE_NAME: str = ""

    def __init__(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        prompts_dir: str = "prompts",
    ) -> None:
        self._agent_id = agent_id
        self._capabilities = capabilities or []
        self._prompt_template = self._load_prompt(prompts_dir)

    # --- 属性 ---

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    @property
    def prompt_template(self) -> str:
        return self._prompt_template

    # --- Prompt 模板加载 ---

    def _load_prompt(self, prompts_dir: str) -> str:
        if not self.PROMPT_FILE:
            return ""
        prompt_path = os.path.join(prompts_dir, self.PROMPT_FILE)
        if not os.path.exists(prompt_path):
            return ""
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    # --- 任务描述构建（核心方法） ---

    @abstractmethod
    async def execute(self, task_payload: dict[str, Any]) -> TaskDescription:
        """
        构建标准化 Task 任务描述

        子类实现：读取 prompt 模板，组装子任务入参和角色 prompt，
        返回 TaskDescription 交给 Trae 运行时调度 Task 子 Agent。

        Args:
            task_payload: 子任务负载

        Returns:
            TaskDescription — 完整的任务描述，可被 Trae Task 工具直接消费
        """
        ...

    def build_task_description(
        self,
        task_id: str,
        user_message: str,
        context_ref: str = "",
        task_type: str = "",
    ) -> TaskDescription:
        """
        构建标准 TaskDescription

        Args:
            task_id:      子任务 ID
            user_message: 用户消息（任务上下文）
            context_ref:  上下文版本号
            task_type:    任务类型

        Returns:
            TaskDescription
        """
        return TaskDescription(
            agent_id=self._agent_id,
            agent_role=self.ROLE_NAME or self._agent_id,
            task_id=task_id,
            task_type=task_type,
            system_prompt=self._prompt_template,
            user_message=user_message,
            output_format=self.OUTPUT_FORMAT,
            context_ref=context_ref,
            metadata={
                "prompt_file": self.PROMPT_FILE,
                "capabilities": self._capabilities,
            },
        )

    # --- 状态上报 ---

    def report_status(self) -> dict[str, Any]:
        """上报状态（供 harness 监控）"""
        return {
            "agent_id": self._agent_id,
            "capabilities": self._capabilities,
            "prompt_loaded": bool(self._prompt_template),
            "prompt_file": self.PROMPT_FILE,
            "status": "idle",
        }