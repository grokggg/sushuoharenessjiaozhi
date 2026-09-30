"""
llm.client — LLM 异步客户端封装

支持 OpenAI-compatible Chat Completions API。
可用环境变量配置：
  - LLM_API_KEY: API 密钥
  - LLM_BASE_URL: API 端点（默认 https://api.openai.com/v1）
  - LLM_MODEL: 模型名称（默认 gpt-4o-mini）
  - LLM_MAX_TOKENS: 最大输出 token（默认 4096）
  - LLM_TEMPERATURE: 温度参数（默认 0.7）
  - LLM_TIMEOUT: 请求超时秒数（默认 120）
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import aiohttp


class LLMClient:
    """
    OpenAI-compatible 异步 LLM 客户端

    Usage:
        client = LLMClient()
        response = await client.chat(
            system_prompt="You are a helpful assistant.",
            user_message="Hello!",
        )
    """

    __slots__ = (
        "_api_key",
        "_base_url",
        "_model",
        "_max_tokens",
        "_temperature",
        "_timeout",
        "_session",
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get(
            "LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")
        )
        self._base_url = (base_url or os.environ.get(
            "LLM_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )).rstrip("/")
        self._model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self._max_tokens = max_tokens or int(os.environ.get("LLM_MAX_TOKENS", "4096"))
        self._temperature = temperature or float(os.environ.get("LLM_TEMPERATURE", "0.7"))
        self._timeout = timeout or int(os.environ.get("LLM_TIMEOUT", "120"))
        self._session: aiohttp.ClientSession | None = None

    # =========================================================================
    # 公开接口
    # =========================================================================

    async def chat(
        self,
        *,
        system_prompt: str = "",
        user_message: str = "",
        messages: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
    ) -> dict[str, Any]:
        """
        发送聊天请求到 LLM

        Args:
            system_prompt: 系统提示词
            user_message:  用户消息
            messages:      完整消息列表（若提供则忽略 system_prompt/user_message）
            temperature:   温度参数（覆盖默认值）
            max_tokens:    最大 token（覆盖默认值）
            response_format: "json_object" 强制 JSON 输出

        Returns:
            {"content": str, "model": str, "usage": dict, "finish_reason": str}
        """
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }

        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        session = await self._get_session()
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                body = await resp.json()

                if resp.status != 200:
                    error_msg = body.get("error", {}).get("message", str(body))
                    return {
                        "content": "",
                        "model": self._model,
                        "usage": {},
                        "finish_reason": "error",
                        "error": f"HTTP {resp.status}: {error_msg}",
                    }

                choice = body.get("choices", [{}])[0]
                return {
                    "content": choice.get("message", {}).get("content", ""),
                    "model": body.get("model", self._model),
                    "usage": body.get("usage", {}),
                    "finish_reason": choice.get("finish_reason", "unknown"),
                }

        except aiohttp.ClientError as exc:
            return {
                "content": "",
                "model": self._model,
                "usage": {},
                "finish_reason": "error",
                "error": f"Network error: {exc}",
            }
        except Exception as exc:
            return {
                "content": "",
                "model": self._model,
                "usage": {},
                "finish_reason": "error",
                "error": f"Unexpected error: {exc}",
            }

    async def chat_json(
        self,
        *,
        system_prompt: str = "",
        user_message: str = "",
        messages: list[dict[str, str]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        发送聊天请求并解析 JSON 响应

        Returns:
            解析后的 dict，或 {"parse_error": str, "raw": str}
        """
        result = await self.chat(
            system_prompt=system_prompt,
            user_message=user_message,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json_object",
        )

        content = result.get("content", "")
        if not content:
            return {
                "parse_error": result.get("error", "Empty response"),
                "raw": content,
            }

        # 尝试多种解析策略
        parsed = self._try_parse_json(content)
        if parsed is not None:
            return parsed

        return {
            "parse_error": "Failed to parse JSON from LLM response",
            "raw": content,
        }

    # =========================================================================
    # 内部方法
    # =========================================================================

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @staticmethod
    def _try_parse_json(content: str) -> dict[str, Any] | None:
        """尝试多种策略解析 JSON"""
        # 策略 1: 直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 策略 2: 提取 markdown 代码块中的 JSON
        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 策略 3: 提取第一个 { 到最后一个 } 之间的内容
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    # =========================================================================
    # 资源管理
    # =========================================================================

    async def close(self) -> None:
        """关闭 HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)