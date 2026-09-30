"""
module_math_b.plugins.plugin_conjecture_generator — 猜想生成器插件

可选插件，默认关闭。通过任务 JSON 显式开启。
基于已有命题池的证明状态和逻辑断层模式，自动生成衍生猜想。

v1.2 业务逻辑版本：基于 GAP_TAXONOMY 和 FALLACY_PATTERN_LIBRARY 实现三种策略。

能力边界：
  - 仅生成猜想描述，不执行验证
  - 不修改假说池状态
  - 不访问核心数学收敛逻辑
  - 每次调用最多生成 5 个猜想

不修改任何 v1.0/v1.1 核心源码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from module_math_b.plugins.plugin_registry import PluginBase, PluginResult, PluginStatus


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class ConjectureCandidate:
    """猜想候选"""
    conjecture_id: str = ""
    statement: str = ""
    source_proposition_id: str = ""
    strategy: str = ""          # weaken | substructure | counter_example_range
    domain: str = "number_theory"
    difficulty: str = "unknown"
    rationale: str = ""         # 生成理由
    expected_branch: str = ""   # PROVEN | DISPROVEN | PENDING


@dataclass
class ConjectureBatch:
    """猜想批次"""
    batch_id: str = ""
    candidates: list[ConjectureCandidate] = field(default_factory=list)
    generation_strategy: str = ""
    source_context: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 猜想生成器
# =============================================================================

class ConjectureGenerator(PluginBase):
    """
    猜想生成器

    三种生成策略：
      1. weaken:              从停滞命题生成弱化版本（缩小定义域、放宽结论）
      2. substructure:        从已证伪命题提取可能成立的子结构
      3. counter_example_range: 从归纳谬误生成反例搜索范围建议

    生命周期：
      1. __init__()          — 初始化
      2. validate_config()   — 校验配置合法性
      3. execute()           — 执行猜想生成
      4. reset()             — 重置内部状态
    """

    plugin_name = "conjecture_generator"

    SUPPORTED_STRATEGIES: set[str] = {
        "weaken", "substructure", "counter_example_range",
    }
    DEFAULT_MAX_CONJECTURES: int = 5
    MAX_CANDIDATE_CACHE: int = 20

    # =========================================================================
    # 弱化变换模板 — 基于谬误模式库的对照表
    # =========================================================================
    WEAKEN_TEMPLATES: list[dict[str, Any]] = [
        # 归纳谬误 → 缩小定义域
        {
            "fallacy_category": "induction_finite_samples",
            "transform": "restrict_domain",
            "description_template": (
                "将命题 '{statement}' 限制在已验证范围 {verified_range} 内，"
                "断言在该范围内成立"
            ),
            "difficulty": "low",
            "expected_branch": "PROVEN",
        },
        # 边界条件遗漏 → 显式排除边界
        {
            "fallacy_category": "boundary_exclusion",
            "transform": "exclude_boundary",
            "description_template": (
                "在命题 '{statement}' 中显式排除边界情况 {boundary_values}，"
                "对剩余定义域重新陈述"
            ),
            "difficulty": "low",
            "expected_branch": "PROVEN",
        },
        # 搜索-存在性混淆 → 弱化为"已知下界"
        {
            "fallacy_category": "search_existence",
            "transform": "weaken_to_lower_bound",
            "description_template": (
                "将命题 '{statement}' 弱化为：在已知搜索范围 {search_range} 内未发现反例"
            ),
            "difficulty": "low",
            "expected_branch": "PROVEN",
        },
        # 概率-确定性混淆 → 弱化为"几乎必然"
        {
            "fallacy_category": "probability_certainty",
            "transform": "weaken_to_probabilistic",
            "description_template": (
                "将命题 '{statement}' 弱化为：该性质对密度为 1 的自然数集合成立"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
        # 默认弱化 → 缩小定义域
        {
            "fallacy_category": "__default__",
            "transform": "restrict_domain",
            "description_template": (
                "将命题 '{statement}' 限制在更小的定义域上，"
                "降低证明难度"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
    ]

    # =========================================================================
    # 子结构提取模板
    # =========================================================================
    SUBSTRUCTURE_TEMPLATES: list[dict[str, Any]] = [
        # 从全称量词提取存在性版本
        {
            "fallacy_category": "induction_finite_samples",
            "transform": "universal_to_existential",
            "description_template": (
                "从命题 '{statement}' 提取弱化版本："
                "存在无穷多个自然数满足该性质"
            ),
            "difficulty": "high",
            "expected_branch": "PENDING",
        },
        # 从反例命题提取子类
        {
            "fallacy_category": "search_existence",
            "transform": "subclass_extraction",
            "description_template": (
                "从命题 '{statement}' 提取子类限制版本："
                "是否存在满足某附加条件的子类使得命题成立？"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
        # 默认子结构
        {
            "fallacy_category": "__default__",
            "transform": "generic_substructure",
            "description_template": (
                "从命题 '{statement}' 提取可能成立的子结构："
                "将命题拆分为更小的独立断言"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
    ]

    # =========================================================================
    # 反例搜索范围模板
    # =========================================================================
    COUNTER_RANGE_TEMPLATES: list[dict[str, Any]] = [
        {
            "fallacy_category": "induction_finite_samples",
            "transform": "expand_search_range",
            "description_template": (
                "基于归纳谬误模式，建议在已验证范围 {verified_range} 之后搜索反例。"
                "典型反例位置：n = {suggested_n}"
            ),
            "difficulty": "low",
            "expected_branch": "DISPROVEN",
        },
        {
            "fallacy_category": "boundary_exclusion",
            "transform": "boundary_counter_search",
            "description_template": (
                "边界条件遗漏：建议在边界值 {boundary_values} 处搜索反例"
            ),
            "difficulty": "low",
            "expected_branch": "DISPROVEN",
        },
        {
            "fallacy_category": "search_existence",
            "transform": "extend_search_range",
            "description_template": (
                "当前搜索范围不足，建议将搜索范围扩展到 {extended_range} 以上"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
        {
            "fallacy_category": "__default__",
            "transform": "generic_counter_search",
            "description_template": (
                "基于断层模式，建议在更大范围内进行系统搜索以寻找反例"
            ),
            "difficulty": "medium",
            "expected_branch": "PENDING",
        },
    ]

    __slots__ = ("_generation_count", "_candidate_cache", "_max_conjectures")

    def __init__(self) -> None:
        self._generation_count: int = 0
        self._candidate_cache: list[ConjectureCandidate] = []
        self._max_conjectures: int = self.DEFAULT_MAX_CONJECTURES

    # =========================================================================
    # 配置校验
    # =========================================================================

    def validate_config(self, config: Any) -> bool:
        from module_math_b.plugins.plugin_registry import PluginConfig
        if not isinstance(config, PluginConfig):
            return False
        extra = config.extra_args if isinstance(config.extra_args, dict) else {}
        max_c = extra.get("max_conjectures", self.DEFAULT_MAX_CONJECTURES)
        if not isinstance(max_c, int) or max_c < 1 or max_c > self.MAX_CANDIDATE_CACHE:
            return False
        strategy = extra.get("strategy", "")
        if strategy and strategy not in self.SUPPORTED_STRATEGIES:
            return False
        return True

    # =========================================================================
    # 执行
    # =========================================================================

    def execute(self, context: dict[str, Any]) -> PluginResult:
        self._generation_count += 1

        try:
            # --- 参数校验 ---
            strategy = context.get("strategy", "")
            if not strategy:
                return self._error_result(
                    "缺少必要参数 'strategy'。"
                    f"支持的策略: {', '.join(sorted(self.SUPPORTED_STRATEGIES))}"
                )
            if strategy not in self.SUPPORTED_STRATEGIES:
                return self._error_result(
                    f"不支持的生成策略: '{strategy}'。"
                    f"支持的策略: {', '.join(sorted(self.SUPPORTED_STRATEGIES))}"
                )
            max_conjectures = context.get("max_conjectures", self.DEFAULT_MAX_CONJECTURES)
            if not isinstance(max_conjectures, int) or max_conjectures < 1:
                return self._error_result(
                    f"max_conjectures 必须为正整数，收到: {max_conjectures}"
                )
            max_conjectures = min(max_conjectures, self.MAX_CANDIDATE_CACHE)

            # --- 上下文提取 ---
            hypothesis_pool = context.get("hypothesis_pool")
            gap_patterns = context.get("gap_patterns", [])
            stagnation_analysis = context.get("stagnation_analysis")
            propositions = context.get("propositions", [])

            # 尝试从 hypothesis_pool 提取命题
            if hypothesis_pool is not None and hasattr(hypothesis_pool, "get_all_propositions"):
                try:
                    pool_props = hypothesis_pool.get_all_propositions()
                    if pool_props:
                        propositions = list(pool_props)
                except Exception:
                    pass

            warnings: list[str] = []
            if not gap_patterns:
                warnings.append("gap_patterns 为空，猜想生成缺乏断层模式参考")
            if not propositions:
                warnings.append("propositions 为空，无源命题可供生成")

            # --- 生成逻辑 ---
            batch_id = f"cg_{self._generation_count}_{strategy}"

            if strategy == "weaken":
                candidates = self._generate_weakened_real(
                    propositions=propositions,
                    gap_patterns=gap_patterns,
                    stagnation_analysis=stagnation_analysis,
                    max_count=max_conjectures,
                    batch_id=batch_id,
                )
            elif strategy == "substructure":
                candidates = self._generate_substructure_real(
                    propositions=propositions,
                    gap_patterns=gap_patterns,
                    max_count=max_conjectures,
                    batch_id=batch_id,
                )
            elif strategy == "counter_example_range":
                candidates = self._generate_counter_range_real(
                    propositions=propositions,
                    gap_patterns=gap_patterns,
                    max_count=max_conjectures,
                    batch_id=batch_id,
                )
            else:
                candidates = []

            # 缓存管理
            self._candidate_cache.extend(candidates)
            if len(self._candidate_cache) > self.MAX_CANDIDATE_CACHE:
                self._candidate_cache = self._candidate_cache[-self.MAX_CANDIDATE_CACHE:]

            batch = ConjectureBatch(
                batch_id=batch_id,
                candidates=candidates,
                generation_strategy=strategy,
                source_context={
                    "gap_pattern_count": len(gap_patterns),
                    "proposition_count": len(propositions),
                    "has_stagnation_analysis": stagnation_analysis is not None,
                },
            )

            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output={
                    "batch": {
                        "batch_id": batch.batch_id,
                        "generation_strategy": batch.generation_strategy,
                        "candidates": [
                            {
                                "conjecture_id": c.conjecture_id,
                                "statement": c.statement,
                                "source_proposition_id": c.source_proposition_id,
                                "strategy": c.strategy,
                                "domain": c.domain,
                                "difficulty": c.difficulty,
                                "rationale": c.rationale,
                                "expected_branch": c.expected_branch,
                            }
                            for c in batch.candidates
                        ],
                        "source_context": batch.source_context,
                    },
                    "candidates": [
                        {
                            "conjecture_id": c.conjecture_id,
                            "statement": c.statement,
                            "strategy": c.strategy,
                        }
                        for c in batch.candidates
                    ],
                    "strategy": strategy,
                    "total_generated": len(candidates),
                    "warnings": warnings,
                    "status_note": "v1.2 业务逻辑版本",
                },
            )

        except Exception as e:
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error=f"猜想生成错误: {type(e).__name__}: {e}",
            )

    # =========================================================================
    # Weaken 策略 — 基于谬误模式库弱化
    # =========================================================================

    def _generate_weakened_real(
        self,
        propositions: list[Any],
        gap_patterns: list[dict[str, Any]],
        stagnation_analysis: Any,
        max_count: int,
        batch_id: str,
    ) -> list[ConjectureCandidate]:
        candidates: list[ConjectureCandidate] = []
        idx = 0

        # 防御性处理：确保 gap_patterns 和 propositions 是列表
        if not isinstance(gap_patterns, list):
            gap_patterns = []
        if not isinstance(propositions, list):
            propositions = []

        # 提取 gap 的分类信息
        gap_categories = self._extract_gap_categories(gap_patterns)

        for prop in propositions:
            if idx >= max_count:
                break

            # 提取命题信息
            statement = self._get_prop_statement(prop)
            prop_id = self._get_prop_id(prop)
            status = self._get_prop_status(prop)

            # 跳过已 PROVEN 的命题（不需要弱化）
            if status == "PROVEN":
                continue

            # 匹配弱点模板
            template = self._match_template(
                gap_categories, self.WEAKEN_TEMPLATES
            )
            verified_range = self._infer_verified_range(statement, gap_patterns)

            description = template["description_template"].format(
                statement=statement,
                verified_range=verified_range or "未知范围",
                boundary_values="{2, 3}",
                search_range="10^6",
            )

            idx += 1
            candidates.append(ConjectureCandidate(
                conjecture_id=f"{batch_id}_w{idx}",
                statement=description,
                source_proposition_id=prop_id,
                strategy="weaken",
                domain="number_theory",
                difficulty=template["difficulty"],
                rationale=f"弱化策略 ({template['transform']}): 基于 {template['fallacy_category']} 模式",
                expected_branch=template["expected_branch"],
            ))

        # 如果没有命题上下文，生成通用弱化
        if not candidates and gap_patterns:
            for gp in gap_patterns[:max_count]:
                idx += 1
                desc = gp.get("description", "未知缺口")
                cat = gp.get("category", "未分类")
                candidates.append(ConjectureCandidate(
                    conjecture_id=f"{batch_id}_w{idx}_generic",
                    statement=f"弱化猜想 [{cat}]: 将存在 '{desc}' 类型缺口的命题限制在已验证范围内",
                    source_proposition_id="",
                    strategy="weaken",
                    domain="number_theory",
                    difficulty="medium",
                    rationale=f"通用弱化: 基于 {cat}",
                    expected_branch="PENDING",
                ))

        return candidates

    # =========================================================================
    # Substructure 策略 — 从已证伪/停滞命题提取子结构
    # =========================================================================

    def _generate_substructure_real(
        self,
        propositions: list[Any],
        gap_patterns: list[dict[str, Any]],
        max_count: int,
        batch_id: str,
    ) -> list[ConjectureCandidate]:
        candidates: list[ConjectureCandidate] = []
        idx = 0
        # 防御性处理
        if not isinstance(gap_patterns, list):
            gap_patterns = []
        if not isinstance(propositions, list):
            propositions = []
        gap_categories = self._extract_gap_categories(gap_patterns)

        for prop in propositions:
            if idx >= max_count:
                break
            statement = self._get_prop_statement(prop)
            prop_id = self._get_prop_id(prop)
            status = self._get_prop_status(prop)

            # 优先从 DISPROVEN 和停滞命题提取子结构
            if status not in ("DISPROVEN", "PENDING", "STAGNANT", ""):
                continue

            template = self._match_template(
                gap_categories, self.SUBSTRUCTURE_TEMPLATES
            )
            description = template["description_template"].format(
                statement=statement,
            )

            idx += 1
            candidates.append(ConjectureCandidate(
                conjecture_id=f"{batch_id}_s{idx}",
                statement=description,
                source_proposition_id=prop_id,
                strategy="substructure",
                domain="number_theory",
                difficulty=template["difficulty"],
                rationale=f"子结构提取 ({template['transform']}): 从状态 {status} 的命题分解",
                expected_branch=template["expected_branch"],
            ))

        if not candidates and gap_patterns:
            for gp in gap_patterns[:max_count]:
                idx += 1
                cat = gp.get("category", "未分类")
                candidates.append(ConjectureCandidate(
                    conjecture_id=f"{batch_id}_s{idx}_generic",
                    statement=f"子结构猜想 [{cat}]: 从含 {cat} 类型断层的命题中提取独立子断言",
                    source_proposition_id="",
                    strategy="substructure",
                    domain="number_theory",
                    difficulty="medium",
                    rationale=f"通用子结构提取: 基于 {cat}",
                    expected_branch="PENDING",
                ))

        return candidates

    # =========================================================================
    # Counter Example Range 策略 — 基于归纳谬误的反例搜索范围
    # =========================================================================

    def _generate_counter_range_real(
        self,
        propositions: list[Any],
        gap_patterns: list[dict[str, Any]],
        max_count: int,
        batch_id: str,
    ) -> list[ConjectureCandidate]:
        candidates: list[ConjectureCandidate] = []
        idx = 0
        # 防御性处理
        if not isinstance(gap_patterns, list):
            gap_patterns = []
        if not isinstance(propositions, list):
            propositions = []
        gap_categories = self._extract_gap_categories(gap_patterns)

        for prop in propositions:
            if idx >= max_count:
                break
            statement = self._get_prop_statement(prop)
            prop_id = self._get_prop_id(prop)
            status = self._get_prop_status(prop)

            # 反例搜索主要针对 DISPROVEN 和 PENDING 命题
            if status not in ("DISPROVEN", "PENDING", "STAGNANT", ""):
                continue

            template = self._match_template(
                gap_categories, self.COUNTER_RANGE_TEMPLATES
            )
            verified_range = self._infer_verified_range(statement, gap_patterns)
            suggested_n = self._infer_suggested_n(statement, gap_patterns)

            description = template["description_template"].format(
                statement=statement,
                verified_range=verified_range or "n ≤ 100",
                suggested_n=suggested_n or "n+1",
                boundary_values="{2, 3}",
                extended_range="10^8",
            )

            idx += 1
            candidates.append(ConjectureCandidate(
                conjecture_id=f"{batch_id}_c{idx}",
                statement=description,
                source_proposition_id=prop_id,
                strategy="counter_example_range",
                domain="number_theory",
                difficulty=template["difficulty"],
                rationale=f"反例搜索 ({template['transform']}): 基于 {template['fallacy_category']}",
                expected_branch=template["expected_branch"],
            ))

        if not candidates and gap_patterns:
            for gp in gap_patterns[:max_count]:
                idx += 1
                cat = gp.get("category", "未分类")
                candidates.append(ConjectureCandidate(
                    conjecture_id=f"{batch_id}_c{idx}_generic",
                    statement=f"反例搜索范围 [{cat}]: 针对 {cat} 类型断层，建议在更大范围内搜索反例",
                    source_proposition_id="",
                    strategy="counter_example_range",
                    domain="number_theory",
                    difficulty="medium",
                    rationale=f"通用反例搜索: 基于 {cat}",
                    expected_branch="DISPROVEN",
                ))

        return candidates

    # =========================================================================
    # 公开接口
    # =========================================================================

    def generate_weakened(self, prop: Any) -> list[dict[str, Any]]:
        """从命题生成弱化版本"""
        statement = self._get_prop_statement(prop)
        prop_id = self._get_prop_id(prop)
        results: list[dict[str, Any]] = []
        for i, tmpl in enumerate(self.WEAKEN_TEMPLATES[:2]):
            results.append({
                "conjecture_id": f"weakened_{prop_id}_{i+1}",
                "statement": tmpl["description_template"].format(
                    statement=statement,
                    verified_range="已验证范围",
                    boundary_values="{2, 3}",
                    search_range="10^6",
                ),
                "strategy": "weaken",
                "transform": tmpl["transform"],
                "difficulty": tmpl["difficulty"],
            })
        return results

    def extract_substructure(self, prop: Any) -> list[dict[str, Any]]:
        """从命题提取子结构"""
        statement = self._get_prop_statement(prop)
        prop_id = self._get_prop_id(prop)
        results: list[dict[str, Any]] = []
        for i, tmpl in enumerate(self.SUBSTRUCTURE_TEMPLATES[:2]):
            results.append({
                "conjecture_id": f"substructure_{prop_id}_{i+1}",
                "statement": tmpl["description_template"].format(statement=statement),
                "strategy": "substructure",
                "transform": tmpl["transform"],
                "difficulty": tmpl["difficulty"],
            })
        return results

    def generate_counter_example_range(self, prop: Any) -> list[dict[str, Any]]:
        """从命题生成反例搜索范围"""
        statement = self._get_prop_statement(prop)
        prop_id = self._get_prop_id(prop)
        results: list[dict[str, Any]] = []
        for i, tmpl in enumerate(self.COUNTER_RANGE_TEMPLATES[:2]):
            results.append({
                "conjecture_id": f"counter_range_{prop_id}_{i+1}",
                "statement": tmpl["description_template"].format(
                    statement=statement,
                    verified_range="n ≤ 100",
                    suggested_n="n+1",
                    boundary_values="{2, 3}",
                    extended_range="10^8",
                ),
                "strategy": "counter_example_range",
                "transform": tmpl["transform"],
                "difficulty": tmpl["difficulty"],
            })
        return results

    # =========================================================================
    # 生命周期
    # =========================================================================

    def reset(self) -> None:
        self._generation_count = 0
        self._candidate_cache.clear()

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _error_result(self, message: str) -> PluginResult:
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ERROR,
            error=message,
        )

    def _extract_gap_categories(self, gap_patterns: list[dict[str, Any]]) -> set[str]:
        """从 gap_patterns 提取分类集合"""
        categories: set[str] = set()
        if not isinstance(gap_patterns, list):
            return categories
        for gp in gap_patterns:
            if isinstance(gp, dict):
                taxonomy_id = gp.get("taxonomy_id", "")
                if taxonomy_id:
                    categories.add(taxonomy_id)
                cat = gp.get("category", "")
                if cat:
                    categories.add(cat)
        return categories

    def _match_template(
        self,
        gap_categories: set[str],
        templates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """根据 gap 分类匹配最佳模板"""
        for tmpl in templates:
            if tmpl["fallacy_category"] == "__default__":
                continue
            if tmpl["fallacy_category"] in gap_categories:
                return tmpl
        # 返回默认模板
        for tmpl in templates:
            if tmpl["fallacy_category"] == "__default__":
                return tmpl
        return templates[-1] if templates else {}

    @staticmethod
    def _get_prop_statement(prop: Any) -> str:
        if isinstance(prop, dict):
            return prop.get("statement", prop.get("statement_text", "未知命题"))
        if hasattr(prop, "statement"):
            return str(getattr(prop, "statement", "未知命题"))
        if hasattr(prop, "statement_text"):
            return str(getattr(prop, "statement_text", "未知命题"))
        return str(prop) if prop else "未知命题"

    @staticmethod
    def _get_prop_id(prop: Any) -> str:
        if isinstance(prop, dict):
            return prop.get("proposition_id", prop.get("id", ""))
        if hasattr(prop, "proposition_id"):
            return str(getattr(prop, "proposition_id", ""))
        return ""

    @staticmethod
    def _get_prop_status(prop: Any) -> str:
        if isinstance(prop, dict):
            return prop.get("status", prop.get("state", ""))
        if hasattr(prop, "status"):
            s = getattr(prop, "status", "")
            if hasattr(s, "value"):
                return str(s.value)
            return str(s)
        if hasattr(prop, "state"):
            return str(getattr(prop, "state", ""))
        return ""

    @staticmethod
    def _infer_verified_range(
        statement: str,
        gap_patterns: list[dict[str, Any]],
    ) -> str:
        """从 gap 描述中推断已验证范围"""
        for gp in gap_patterns:
            if isinstance(gp, dict):
                desc = gp.get("description", "")
                # 尝试提取数字范围
                m = re.search(r'(\d+)\s*个?\s*特例', desc)
                if m:
                    n = int(m.group(1))
                    return f"n ≤ {n - 1}"
                m = re.search(r'前\s*(\d+)', desc)
                if m:
                    n = int(m.group(1))
                    return f"n ≤ {n - 1}"
        return "已验证范围"

    @staticmethod
    def _infer_suggested_n(
        statement: str,
        gap_patterns: list[dict[str, Any]],
    ) -> str:
        """推断建议的反例搜索起点"""
        for gp in gap_patterns:
            if isinstance(gp, dict):
                desc = gp.get("description", "")
                m = re.search(r'(\d+)\s*个?\s*特例', desc)
                if m:
                    return str(int(m.group(1)))
                m = re.search(r'前\s*(\d+)', desc)
                if m:
                    return str(int(m.group(1)))
        return "n+1"

    @property
    def generation_count(self) -> int:
        return self._generation_count

    @property
    def cached_candidates(self) -> list[ConjectureCandidate]:
        return list(self._candidate_cache)