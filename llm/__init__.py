"""
llm — LLM 调用封装层

提供 OpenAI-compatible API 的异步客户端封装。
所有 Agent 通过此模块调用大模型，保持架构干净。
"""

from llm.client import LLMClient

__all__ = ["LLMClient"]