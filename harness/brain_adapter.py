"""
harness.brain_adapter — B1 仿真内核适配层

在遵循 B1-Final 冻结约束的前提下，通过适配器模式增强 B1 基准的区分度。
B1 内核本身不可修改，但适配层可以：
  1. 分析输入上下文的质量维度（数据丰富度、证据链长度、逻辑一致性）
  2. 将分析结果映射为差异化的基准置信度
  3. 保留 B1 原始推理结果作为参考

设计原则：
  - 不修改 B1 内核任何代码
  - 不直接实例化 BrainKernel
  - 所有增强逻辑在适配层完成
  - 适配层输出在元规则③中作为"增强基准"使用
"""

from __future__ import annotations

import re
from typing import Any

from brain_subsystem.interface import BrainInterface
from brain_subsystem.constants import BRAIN_CONSTANTS


class BrainAdapter:
    """
    B1 仿真内核适配器

    包装 BrainInterface，在不修改冻结内核的前提下，
    提供基于上下文质量分析的差异化基准响应。

    核心机制：
    1. 调用 B1 原始推理（获得原始结果）
    2. 分析上下文质量（数据丰富度、证据链、逻辑一致性）
    3. 计算质量调整因子
    4. 输出差异化增强基准
    """

    __slots__ = ("_brain", "_quality_history")

    def __init__(self, brain: BrainInterface | None = None) -> None:
        self._brain = brain or BrainInterface()
        self._quality_history: list[float] = []

    # =========================================================================
    # 核心方法：差异化推理
    # =========================================================================

    def enhanced_inference(
        self,
        context: str,
        worker_outputs: dict[str, Any] | None = None,
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        执行增强推理：B1 原始推理 + 上下文质量分析 → 差异化基准

        Args:
            context:        推理上下文
            worker_outputs: 各 Agent 原始输出（用于质量分析）
            depth:          推理深度

        Returns:
            {
                "confidence": float,           # 差异化基准置信度
                "raw_b1_confidence": float,    # B1 原始置信度（参考）
                "quality_score": float,        # 上下文质量评分 [0,1]
                "quality_factors": dict,       # 各维度质量分解
                "inference": str,              # 推理文本
                "depth": int,
                "is_stable": bool,
            }
        """
        # 1. 调用 B1 原始推理
        raw_result = self._brain.run_inference(context=context, depth=depth)

        # 2. 分析上下文质量
        quality_score, quality_factors = self._analyze_context_quality(
            context, worker_outputs
        )
        self._quality_history.append(quality_score)

        # 3. 计算差异化基准
        raw_confidence = raw_result.get("confidence", 0.5)
        # 质量评分映射到 [0.3, 0.8] 区间，保持与 B1 原始值的中等偏离
        adjusted_confidence = 0.3 + quality_score * 0.5
        # 与 B1 原始值加权融合，保留 B1 30% 的权重
        blended_confidence = raw_confidence * 0.3 + adjusted_confidence * 0.7

        # 4. 稳态检测
        is_stable = self._brain.is_homeostatic(
            self._quality_history[-BRAIN_CONSTANTS.HOMEOSTASIS_WINDOW_SIZE:]
            if len(self._quality_history) >= BRAIN_CONSTANTS.HOMEOSTASIS_WINDOW_SIZE
            else [quality_score] * BRAIN_CONSTANTS.HOMEOSTASIS_WINDOW_SIZE
        )

        return {
            "confidence": round(blended_confidence, 4),
            "raw_b1_confidence": raw_confidence,
            "quality_score": round(quality_score, 4),
            "quality_factors": quality_factors,
            "inference": raw_result.get("inference", ""),
            "depth": depth,
            "is_stable": is_stable,
        }

    # =========================================================================
    # 上下文质量分析
    # =========================================================================

    def _analyze_context_quality(
        self,
        context: str,
        worker_outputs: dict[str, Any] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """
        分析输入上下文的质量

        维度：
        1. 数据丰富度：观测数据点数量、来源多样性
        2. 证据链完整性：从观测到结论的链路数量
        3. 逻辑一致性：Agent 间结论的一致性程度
        4. 批判深度：怀疑批判和红队测试的覆盖度

        Returns:
            (quality_score, {factor_name: score})
        """
        factors: dict[str, float] = {}

        # 因子 1: 数据丰富度
        factors["data_richness"] = self._score_data_richness(worker_outputs)

        # 因子 2: 证据链完整性
        factors["evidence_completeness"] = self._score_evidence_chain(worker_outputs)

        # 因子 3: 逻辑一致性
        factors["logical_coherence"] = self._score_logical_coherence(worker_outputs)

        # 因子 4: 批判深度
        factors["critique_depth"] = self._score_critique_depth(worker_outputs)

        # 因子 5: 上下文长度（信息量代理）
        factors["context_information"] = min(1.0, len(context) / 2000.0)

        # 加权计算
        weights = {
            "data_richness": 0.30,
            "evidence_completeness": 0.25,
            "logical_coherence": 0.20,
            "critique_depth": 0.15,
            "context_information": 0.10,
        }

        quality_score = sum(
            factors[k] * weights.get(k, 0.0) for k in factors
        )
        quality_score = max(0.1, min(1.0, quality_score))

        return quality_score, factors

    def _score_data_richness(self, worker_outputs: dict[str, Any] | None) -> float:
        """评分：数据丰富度"""
        if not worker_outputs:
            return 0.3
        total_obs = 0
        for output in worker_outputs.values():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    observations = inner.get("observations", [])
                    total_obs += len(observations) if isinstance(observations, list) else 0
        # 0 个观测 → 0.1, 5 个 → 0.5, 15+个 → 1.0
        return min(1.0, 0.1 + total_obs * 0.06)

    def _score_evidence_chain(self, worker_outputs: dict[str, Any] | None) -> float:
        """评分：证据链完整性"""
        if not worker_outputs:
            return 0.3
        # 检查是否有归档 Agent 输出的证据链
        for output in worker_outputs.values():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    chains = inner.get("evidence_chain", [])
                    if isinstance(chains, list) and len(chains) > 0:
                        return min(1.0, len(chains) * 0.2)
        return 0.3

    def _score_logical_coherence(self, worker_outputs: dict[str, Any] | None) -> float:
        """评分：逻辑一致性"""
        if not worker_outputs or len(worker_outputs) < 2:
            return 0.5
        # 检查 Agent 输出中是否有显式矛盾
        confidences = []
        for output in worker_outputs.values():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    conf = inner.get("confidence")
                    if isinstance(conf, (int, float)):
                        confidences.append(conf)
        if len(confidences) < 2:
            return 0.5
        mean_conf = sum(confidences) / len(confidences)
        variance = sum((c - mean_conf) ** 2 for c in confidences) / len(confidences)
        # 方差越小，一致性越高
        return max(0.1, 1.0 - variance * 2.0)

    def _score_critique_depth(self, worker_outputs: dict[str, Any] | None) -> float:
        """评分：批判深度"""
        if not worker_outputs:
            return 0.3
        total_critiques = 0
        total_red_team = 0
        for output in worker_outputs.values():
            if isinstance(output, dict):
                inner = output.get("output", output)
                if isinstance(inner, dict):
                    critiques = inner.get("critiques", [])
                    red_cases = inner.get("red_team_cases", [])
                    total_critiques += len(critiques) if isinstance(critiques, list) else 0
                    total_red_team += len(red_cases) if isinstance(red_cases, list) else 0
        combined = total_critiques + total_red_team
        return min(1.0, 0.2 + combined * 0.1)

    # =========================================================================
    # 兼容 BrainInterface 的委托方法
    # =========================================================================

    def run_inference(self, context: str, depth: int = 1) -> dict[str, Any]:
        """委托给 BrainInterface，保持接口兼容"""
        return self._brain.run_inference(context=context, depth=depth)

    def compute_oscillation(self, t: float) -> float:
        """委托给 BrainInterface"""
        return self._brain.compute_oscillation(t)

    def is_homeostatic(self, values: list[float]) -> bool:
        """委托给 BrainInterface"""
        return self._brain.is_homeostatic(values)

    def get_kernel_state(self) -> dict[str, Any]:
        """委托给 BrainInterface"""
        return self._brain.get_kernel_state()

    @property
    def quality_history(self) -> list[float]:
        return list(self._quality_history)