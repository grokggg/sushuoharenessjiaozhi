"""
module_math_b.plugins.stagnation_analyzer — 停滞根因分析插件

可选插件，默认关闭。通过任务 JSON 显式开启。
分析数学迭代停滞的根本原因，生成诊断报告。

不修改任何 v1.0 核心源码。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from module_math_b.plugins.plugin_registry import PluginBase, PluginResult, PluginStatus


@dataclass
class StagnationDiagnosis:
    """停滞诊断"""
    root_cause: str = ""
    severity: str = "low"  # low | medium | high | critical
    gap_patterns: list[str] = field(default_factory=list)
    suggestion: str = ""
    affected_propositions: list[str] = field(default_factory=list)


class StagnationAnalyzer(PluginBase):
    """
    停滞根因分析

    分析维度：
      1. 缺口模式识别：重复出现的 gap 类型
      2. 推导停滞检测：连续多轮无新步骤
      3. 反例生成率：反例生成停滞
      4. 审查循环：同一问题反复出现
      5. 命题复杂度：命题本身是否过于困难

    v1.1.1 增强：细粒度停滞模式库 + 分类体系
    """

    plugin_name = "stagnation_analyzer"

    # 严重性排序（数值越大越严重）
    _SEVERITY_ORDER: dict[str, int] = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }

    # =========================================================================
    # 停滞模式库 (Stagnation Pattern Library) — v1.1.1 固化
    # =========================================================================
    STAGNATION_PATTERNS: list[dict[str, Any]] = [
        {
            "pattern_id": "SP-001",
            "name": "系统性缺口停滞",
            "category": "logical_gap_recurrence",
            "severity_implication": "high",
            "description": "同一类逻辑断层重复出现≥3次，表明缺少关键引理或证明框架",
            "regex_patterns": [
                r"最常见缺口.*出现\s*(\d+)\s*次",
            ],
            "suggestion": "建议识别缺口共性，补充缺失的引理或中间结论，建立中间层抽象",
        },
        {
            "pattern_id": "SP-002",
            "name": "推导质量退化",
            "category": "derivation_quality_decay",
            "severity_implication": "medium",
            "description": "校验平均分持续低于0.5，推导质量无法支撑有效收敛",
            "regex_patterns": [
                r"校验平均分仅\s*([\d.]+)",
            ],
            "suggestion": "建议重新审视命题前提和推导规则，检查是否存在概念混淆",
        },
        {
            "pattern_id": "SP-003",
            "name": "长期停滞",
            "category": "prolonged_stagnation",
            "severity_implication": "critical",
            "description": "连续≥3轮无新推导步骤，系统陷入完全停滞",
            "regex_patterns": [
                r"连续\s*(\d+)\s*轮.*无新推导",
            ],
            "suggestion": "建议切换证明策略或引入新的数学工具，考虑将命题分解为子问题",
        },
        {
            "pattern_id": "SP-004",
            "name": "资源分散",
            "category": "resource_dispersion",
            "severity_implication": "medium",
            "description": "同时处理过多命题（>3个），导致每个命题的推导深度不足",
            "regex_patterns": [
                r"同时处理\s*(\d+)\s*个命题",
            ],
            "suggestion": "建议聚焦核心命题，减少并行度，优先处理难度最低的命题",
        },
        {
            "pattern_id": "SP-005",
            "name": "命题难度过高",
            "category": "intrinsic_difficulty",
            "severity_implication": "low",
            "description": "命题可能属于著名的开放问题，当前工具链无法在规定轮次内收敛",
            "regex_patterns": [
                r"未检测到明显停滞原因",
                r"命题本身难度过高",
            ],
            "suggestion": "建议人工介入，评估命题是否为已知开放问题，考虑降低命题难度",
        },
    ]

    # 按停滞类型映射的针对性建议
    _TYPED_SUGGESTIONS: dict[str, list[str]] = {
        "logical_gap_recurrence": [
            "建议识别缺口共性，补充缺失的引理或中间结论",
            "建议建立中间层抽象，将多步推理合并为可复用引理",
        ],
        "derivation_quality_decay": [
            "建议重新审视命题前提和推导规则",
            "建议检查是否存在概念混淆或符号滥用",
            "建议增加定义域约束，缩小证明范围",
        ],
        "prolonged_stagnation": [
            "建议切换证明策略（直接证法↔反证法↔构造法）",
            "建议引入新的数学工具或变换视角",
            "建议将命题分解为更小的子问题",
        ],
        "resource_dispersion": [
            "建议聚焦核心命题，减少并行度",
            "建议按难度排序，优先处理可快速收敛的命题",
        ],
        "intrinsic_difficulty": [
            "建议人工介入，评估命题是否可解",
            "建议查阅文献，确认是否为已知开放问题",
            "建议降低命题难度或缩小范围",
        ],
    }

    __slots__ = ("_gap_history", "_round_metrics")

    def __init__(self) -> None:
        self._gap_history: dict[str, list[str]] = {}
        self._round_metrics: list[dict[str, Any]] = []

    def execute(self, context: dict[str, Any]) -> PluginResult:
        """
        分析停滞根因

        context 期望字段:
          - propositions:      命题列表
          - round_number:      当前轮次
          - stagnation_rounds: 停滞轮数
          - derivation_steps:  推导步骤
          - validation_reports: 校验报告
          - gap_patterns:      已知缺口模式
        """
        try:
            propositions = context.get("propositions", [])
            stagnation_rounds = context.get("stagnation_rounds", 0)
            round_number = context.get("round_number", 0)

            diagnosis = self._analyze(context)

            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={
                    "diagnosis": diagnosis,
                    "stagnation_rounds": stagnation_rounds,
                    "round_number": round_number,
                    "proposition_count": len(propositions),
                },
            )
        except Exception as e:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error=f"分析错误: {e}",
            )

    def _analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        """执行停滞根因分析（v1.1.1 增强：含模式匹配与分类）"""
        propositions = context.get("propositions", [])
        stagnation_rounds = context.get("stagnation_rounds", 0)
        validation_reports = context.get("validation_reports", [])
        derivation_steps = context.get("derivation_steps", [])
        gap_patterns_input = context.get("gap_patterns", [])

        root_causes: list[str] = []
        suggestions: list[str] = []
        gap_patterns: list[str] = []
        severity = "low"
        matched_patterns: list[str] = []

        # 1. 缺口模式识别
        gap_types: dict[str, int] = {}
        for step in derivation_steps:
            if isinstance(step, dict):
                if step.get("has_gap"):
                    desc = step.get("gap_description", "未指定")
                    gap_types[desc] = gap_types.get(desc, 0) + 1

        if gap_types:
            most_common = max(gap_types, key=gap_types.get)  # type: ignore[arg-type]
            gap_patterns.append(f"最常见缺口: '{most_common}' (出现 {gap_types[most_common]} 次)")
            if gap_types[most_common] >= 3:
                root_causes.append("存在系统性推导缺口，可能缺少关键引理")
                suggestions.extend(self._get_typed_suggestions("logical_gap_recurrence"))
                severity = self._max_severity(severity, "high")
                matched_patterns.append("SP-001")

        # 2. 推导停滞
        if stagnation_rounds >= 3:
            root_causes.append(f"连续 {stagnation_rounds} 轮无新推导步骤")
            severity = self._max_severity(severity, "critical")
            suggestions.extend(self._get_typed_suggestions("prolonged_stagnation"))
            matched_patterns.append("SP-003")

        # 3. 校验报告分析（增强：细粒度诊断）
        if validation_reports:
            total_score = 0
            gap_details: list[dict[str, Any]] = []
            for r in validation_reports:
                if isinstance(r, dict):
                    total_score += r.get("overall_score", 0)
                    # 收集 gap 详情用于分类
                    for g in r.get("logical_gaps", []):
                        gap_details.append(g)
            avg_score = total_score / len(validation_reports) if validation_reports else 0
            if avg_score < 0.5:
                # 细粒度：根据分值区间给出不同诊断
                if avg_score < 0.2:
                    root_causes.append(
                        f"校验平均分仅 {avg_score:.2f}（严重退化），推导框架存在结构性缺陷"
                    )
                elif avg_score < 0.4:
                    root_causes.append(
                        f"校验平均分仅 {avg_score:.2f}（中度退化），推导质量持续偏低"
                    )
                else:
                    root_causes.append(
                        f"校验平均分仅 {avg_score:.2f}（轻度退化），建议优化推导逻辑"
                    )
                suggestions.extend(self._get_typed_suggestions("derivation_quality_decay"))
                matched_patterns.append("SP-002")

            # 4. 缺口分类统计
            if gap_details:
                gap_categories: dict[str, int] = {}
                for g in gap_details:
                    cat = g.get("category", "未分类")
                    gap_categories[cat] = gap_categories.get(cat, 0) + 1
                if gap_categories:
                    category_summary = ", ".join(
                        f"{cat}:{cnt}次" for cat, cnt in gap_categories.items()
                    )
                    gap_patterns.append(f"缺口分类分布: {category_summary}")

        # 5. 命题复杂度
        if len(propositions) > 3:
            root_causes.append(f"同时处理 {len(propositions)} 个命题，可能资源分散")
            suggestions.extend(self._get_typed_suggestions("resource_dispersion"))
            matched_patterns.append("SP-004")

        if not root_causes:
            root_causes.append("未检测到明显停滞原因，可能是命题本身难度过高")
            suggestions.extend(self._get_typed_suggestions("intrinsic_difficulty"))
            matched_patterns.append("SP-005")

        if severity == "low" and stagnation_rounds >= 2:
            severity = "medium"

        # 6. 分类诊断增强
        classification = self._classify_stagnation(
            root_causes=root_causes,
            stagnation_rounds=stagnation_rounds,
            avg_score=avg_score if validation_reports else None,
            proposition_count=len(propositions),
            matched_patterns=matched_patterns,
        )

        return {
            "root_causes": root_causes,
            "severity": severity,
            "gap_patterns": gap_patterns,
            "suggestions": suggestions,
            "stagnation_rounds": stagnation_rounds,
            "gap_type_count": len(gap_types),
            "total_gaps": sum(gap_types.values()),
            "stagnation_classification": classification,
            "matched_patterns": matched_patterns,
        }

    def reset(self) -> None:
        self._gap_history.clear()
        self._round_metrics.clear()

    @classmethod
    def _max_severity(cls, a: str, b: str) -> str:
        """取两个严重性级别中较高的一个"""
        return a if cls._SEVERITY_ORDER.get(a, 0) >= cls._SEVERITY_ORDER.get(b, 0) else b

    @classmethod
    def _get_typed_suggestions(cls, category: str) -> list[str]:
        """获取按停滞类型分类的针对性建议"""
        return cls._TYPED_SUGGESTIONS.get(category, ["建议人工介入审查"])

    @classmethod
    def _classify_stagnation(
        cls,
        root_causes: list[str],
        stagnation_rounds: int,
        avg_score: float | None,
        proposition_count: int,
        matched_patterns: list[str],
    ) -> dict[str, Any]:
        """
        对停滞状态进行细粒度分类诊断

        Returns:
            dict with keys: primary_category, secondary_factors, confidence, recommended_action
        """
        result: dict[str, Any] = {
            "primary_category": "unknown",
            "secondary_factors": [],
            "confidence": "low",
            "recommended_action": "人工审查",
        }

        # 模式匹配
        if "SP-003" in matched_patterns:
            result["primary_category"] = "prolonged_stagnation"
            result["secondary_factors"] = [p for p in matched_patterns if p != "SP-003"]
            result["confidence"] = "high"
            result["recommended_action"] = "强制终止并切换策略"
        elif "SP-001" in matched_patterns:
            result["primary_category"] = "logical_gap_recurrence"
            result["secondary_factors"] = [p for p in matched_patterns if p != "SP-001"]
            result["confidence"] = "high"
            result["recommended_action"] = "补充缺失引理"
        elif "SP-002" in matched_patterns:
            result["primary_category"] = "derivation_quality_decay"
            if avg_score is not None:
                if avg_score < 0.2:
                    result["confidence"] = "high"
                    result["recommended_action"] = "重构推导框架"
                else:
                    result["confidence"] = "medium"
                    result["recommended_action"] = "优化推导逻辑"
            result["secondary_factors"] = [p for p in matched_patterns if p != "SP-002"]
        elif "SP-004" in matched_patterns:
            result["primary_category"] = "resource_dispersion"
            result["confidence"] = "medium"
            result["recommended_action"] = "聚焦核心命题"
        elif "SP-005" in matched_patterns:
            result["primary_category"] = "intrinsic_difficulty"
            result["confidence"] = "medium"
            result["recommended_action"] = "降低命题难度或人工介入"

        # 补充上下文
        if avg_score is not None:
            result["avg_validation_score"] = round(avg_score, 2)
        result["stagnation_rounds"] = stagnation_rounds
        result["proposition_count"] = proposition_count

        return result