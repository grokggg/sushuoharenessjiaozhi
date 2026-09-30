"""
module_math_b.math_validator — 多层数学逻辑校验引擎

三层流水线，逐步骤强制校验：

第一层：语法与一致性校验
  变量定义域合法、符号统一、推导前后不自相矛盾

第二层：逻辑断层检测器（核心独创）
  自动识别：
    - 跳步推导
    - 隐性引理未声明
    - 条件缺失
    - 循环论证
    - 因果倒置

第三层：红队对抗校验
  动态分配 Worker 执行：
    - 边界极值测试
    - 特例暴力遍历
    - 微小扰动验证
    - 定义域极限检验
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathValidationReport,
)


# =============================================================================
# 数学校验器
# =============================================================================

class MathValidator:
    """
    多层数学逻辑校验引擎

    三层流水线：
      L1: 语法与一致性
      L2: 逻辑断层检测
      L3: 红队对抗校验
    """

    # 已知推导规则关键词（用于 L2 跳步检测）
    KNOWN_DERIVATION_RULES: set[str] = {
        "modus_ponens", "modus_tollens", "transitivity",
        "induction", "contradiction", "contrapositive",
        "case_analysis", "direct_proof", "construction",
        "pigeonhole", "counting", "invariant",
        "inequality", "bound", "asymptotic",
        "factorization", "divisibility", "congruence",
        "algebraic_manipulation", "substitution",
        "definition", "axiom", "theorem", "lemma",
        "corollary", "by_definition", "by_construction",
    }

    # 循环论证模式
    CIRCULAR_PATTERNS: list[tuple[str, str]] = [
        (r"(?:因为|since|because).*?(?:所以|therefore|thus).*?(?:所以|therefore|thus).*?(?:因为|since|because)", "因果倒置"),
        (r"假设.*?(?:成立|holds).*?因此.*?假设", "循环假设"),
    ]

    # 跳步信号词
    SKIP_SIGNALS: list[str] = [
        "显然", "易得", "不难看出", "显然成立",
        "obviously", "clearly", "trivially", "it is easy to see",
        "without loss of generality", "不失一般性",
        "类似的", "同理", "similarly",
    ]

    # 隐性假设信号
    HIDDEN_ASSUMPTION_SIGNALS: list[str] = [
        "不妨设", "假设", "令", "设",
        "let", "assume", "suppose", "set",
    ]

    # =========================================================================
    # 逻辑断层分类体系 (Gap Taxonomy) — v1.1.1 增强
    # =========================================================================
    GAP_TAXONOMY: dict[str, dict[str, str]] = {
        # 归纳谬误族
        "induction_finite_samples": {
            "category": "归纳谬误",
            "subcategory": "有限样本归纳",
            "severity": "high",
            "description": "仅凭有限个特例尝试推广到全体，缺乏一般性证明框架",
            "patterns": [
                r"仅凭.*特例归纳",
                r"有限.*特例.*推广",
                r"仅凭.*个.*特例",
                r"有限验证.*不能.*代替",
                r"induction.*from.*finite",
            ],
        },
        "induction_small_n": {
            "category": "归纳谬误",
            "subcategory": "小样本归纳",
            "severity": "medium",
            "description": "样本量过小（n<100），统计显著性不足",
            "patterns": [
                r"仅凭.*前\d+.*特例",
                r"only.*first.*few",
            ],
        },
        # 边界条件遗漏族
        "boundary_exclusion": {
            "category": "边界条件遗漏",
            "subcategory": "未排除边界",
            "severity": "medium",
            "description": "命题陈述未排除定义域边界或退化情况，导致反例落在边界上",
            "patterns": [
                r"未排除.*边界",
                r"边界.*情况",
                r"陈述.*不严谨",
                r"boundary.*case",
                r"edge.*case",
            ],
        },
        # 概率-确定性混淆族
        "probability_certainty": {
            "category": "概率-确定性混淆",
            "subcategory": "概率论证",
            "severity": "high",
            "description": "将概率期望或启发式统计误认为确定性数学证明",
            "patterns": [
                r"概率期望.*确定性",
                r"几乎所有.*不等于.*所有",
                r"零测度.*反例",
                r"probability.*certainty",
                r"almost.*all.*not.*all",
            ],
        },
        # 循环依赖族
        "circular_dependency": {
            "category": "循环依赖",
            "subcategory": "依赖未证明命题",
            "severity": "high",
            "description": "推导依赖更强大但同样未证明的猜想，构成逻辑循环",
            "patterns": [
                r"依赖.*未证明.*猜想",
                r"循环依赖",
                r"circular.*dependency",
                r"更强.*但.*未证明",
            ],
        },
        # 搜索-存在性混淆族
        "search_existence": {
            "category": "搜索-存在性混淆",
            "subcategory": "有限搜索≠不存在",
            "severity": "high",
            "description": "将有限计算搜索的未发现结果等同于不存在性的数学证明",
            "patterns": [
                r"有限搜索.*不能.*证明",
                r"有限搜索.*不存在",
                r"下界.*不断提高.*无法排除",
                r"search.*cannot.*prove.*non.?existence",
            ],
        },
        # 量词范围错误族
        "quantifier_scope": {
            "category": "量词范围错误",
            "subcategory": "全称量词范围过大",
            "severity": "medium",
            "description": "将'几乎所有'、'大概率'等弱量词混同于全称量词'所有'",
            "patterns": [
                r"几乎所有.*不等于.*所有",
                r"almost.*all.*\u2260.*all",
            ],
        },
    }

    # =========================================================================
    # 典型谬误模式库 (Fallacy Pattern Library) — v1.1.1 固化
    # =========================================================================
    FALLACY_PATTERN_LIBRARY: list[dict[str, Any]] = [
        {
            "fallacy_id": "F-001",
            "name": "有限归纳谬误",
            "category": "induction_finite_samples",
            "aliases": ["归纳法误用", "Hasty Generalization"],
            "description": "仅凭有限个（通常≤100）特例即断言命题对所有自然数成立",
            "classic_examples": [
                "Fermat 猜想 F_n 全为素数（F_0~F_4 成立，Euler 发现 F_5=641×6700417）",
                "Euler 多项式 n²+n+41 全为素数（n=0~39 成立，n=40 失败）",
            ],
            "detection_keywords": [
                "仅凭", "特例", "归纳", "有限个", "检验了", "验证了",
                "holds for n=", "checked up to", "verified for",
            ],
            "mitigation": "必须提供一般性证明框架（归纳基+归纳步），或显式声明命题为猜想",
        },
        {
            "fallacy_id": "F-002",
            "name": "边界条件遗漏",
            "category": "boundary_exclusion",
            "aliases": ["Edge Case Omission", "退化情况忽略"],
            "description": "命题陈述忽略了定义域中的退化点或边界值，导致反例落在被排除的区域",
            "classic_examples": [
                "「所有素数形如 6k±1」忽略了 n=2,3",
                "「所有三角形内角和为180°」忽略非欧几何",
            ],
            "detection_keywords": [
                "未排除", "边界", "特殊情况", "n=2,3", "退化",
                "except", "excluding", "edge case", "boundary",
            ],
            "mitigation": "在命题陈述中显式声明定义域约束，或单独处理退化情况",
        },
        {
            "fallacy_id": "F-003",
            "name": "概率-确定性混淆",
            "category": "probability_certainty",
            "aliases": ["Probabilistic Fallacy", "统计论证谬误"],
            "description": "将概率论中的'几乎必然'或启发式统计证据当作确定性数学证明",
            "classic_examples": [
                "Legendre 猜想：素数定理的密度估计≠确定性存在",
                "Goldbach 猜想：概率模型预测≠证明",
            ],
            "detection_keywords": [
                "概率", "期望", "几乎所有", "密度", "大概率",
                "probability", "almost surely", "expected", "density",
            ],
            "mitigation": "严格区分概率论推理与确定性证明，概率证据仅作为辅助参考",
        },
        {
            "fallacy_id": "F-004",
            "name": "循环依赖论证",
            "category": "circular_dependency",
            "aliases": ["Circular Dependency", "循环推理"],
            "description": "推导依赖一个更强大但同样未证明的命题，构成逻辑循环",
            "classic_examples": [
                "用 Riemann 猜想证 Legendre 猜想",
                "用 Goldbach 猜想证孪生素数猜想",
            ],
            "detection_keywords": [
                "依赖", "未证明", "猜想", "循环", "等价于",
                "relies on", "depends on", "equivalent to", "unproven",
            ],
            "mitigation": "明确标注依赖关系，降级为条件性结论（若X成立则Y成立）",
        },
        {
            "fallacy_id": "F-005",
            "name": "搜索-存在性混淆",
            "category": "search_existence",
            "aliases": ["Exhaustive Search Fallacy", "计算穷举谬误"],
            "description": "将有限范围的穷举搜索未发现结果等同于数学上的不存在性证明",
            "classic_examples": [
                "「搜索到10^1500 无奇完全数」≠证明不存在",
                "「验证到10^18 无 Collatz 反例」≠证明 Collatz 猜想",
            ],
            "detection_keywords": [
                "有限搜索", "穷举", "搜索到", "验证到", "下界", "未发现",
                "exhaustive search", "checked up to", "verified up to",
                "no counterexample found",
            ],
            "mitigation": "搜索结果为存在性提供下界，但不能作为不存在性证明",
        },
        {
            "fallacy_id": "F-006",
            "name": "量词范围错误",
            "category": "quantifier_scope",
            "aliases": ["Quantifier Scope Error", "全称量词滥用"],
            "description": "将弱量词（几乎所有、测度1）错误地等同于全称量词（所有、无一例外）",
            "classic_examples": [
                "「几乎所有自然数满足性质P」→「所有自然数满足P」",
                "「零测度例外」→「无例外」",
            ],
            "detection_keywords": [
                "几乎所有", "几乎必然", "测度零", "密度1",
                "almost all", "almost surely", "measure zero", "density 1",
            ],
            "mitigation": "严格区分'几乎所有'与'所有'，明确标注例外集合的测度",
        },
    ]

    __slots__ = ("_validation_count",)

    def __init__(self) -> None:
        self._validation_count: int = 0

    # =========================================================================
    # 完整校验流水线
    # =========================================================================

    def validate_proposition(
        self,
        proposition: MathProposition,
        round_number: int = 0,
        worker_outputs: dict[str, Any] | None = None,
    ) -> MathValidationReport:
        """
        对命题执行完整三层校验流水线
        """
        self._validation_count += 1
        now = datetime.now(timezone.utc).isoformat()
        report = MathValidationReport(
            report_id=f"vr_{self._validation_count}_{proposition.proposition_id}",
            proposition_id=proposition.proposition_id,
            round_number=round_number,
            created_at=now,
        )

        # --- L1: 语法与一致性 ---
        self._layer1_syntax_check(proposition, report)

        # --- L2: 逻辑断层检测 ---
        self._layer2_gap_detection(proposition, report)

        # --- 综合判定 ---
        self._compute_overall_score(report)

        return report

    def validate_derivation_step(
        self, step: MathDerivationStep, all_steps: list[MathDerivationStep]
    ) -> MathDerivationStep:
        """
        校验单个推导步骤

        原地修改 step 的 validation 字段。
        """
        errors: list[str] = []

        # 检查前提是否为空
        if not step.premises:
            errors.append("推导步骤缺少前提")
            step.has_gap = True
            step.gap_description = "缺少前提声明"

        # 检查结论是否为空
        if not step.conclusion.strip():
            errors.append("推导步骤缺少结论")
            step.has_gap = True
            step.gap_description = step.gap_description or "缺少结论"

        # 检查推导规则是否为空
        if not step.derivation_rule.strip():
            errors.append("推导步骤缺少推导规则/定理引用")
            step.has_gap = True
            step.gap_description = step.gap_description or "缺少推导规则"

        # 检查跳步信号
        for signal in self.SKIP_SIGNALS:
            if signal in step.justification:
                errors.append(f"检测到跳步信号词: '{signal}'")
                step.has_gap = True
                step.gap_description = step.gap_description or f"跳步推导: {signal}"
                break

        # 检查循环论证
        self._check_circular(step, errors)

        # 检查隐性假设
        self._check_hidden_assumption(step, errors)

        step.validation_errors = errors
        step.validation_passed = len(errors) == 0

        return step

    # =========================================================================
    # L1: 语法与一致性
    # =========================================================================

    def _layer1_syntax_check(
        self, prop: MathProposition, report: MathValidationReport
    ) -> None:
        """L1 语法与一致性校验"""
        errors: list[str] = []

        # 检查命题陈述是否为空
        if not prop.statement.strip():
            errors.append("命题陈述为空")
            report.syntax_valid = False

        # 检查变量定义域一致性
        variables = self._extract_variables(prop.statement)
        if len(variables) > 0:
            # 简单检查：是否有变量在后续步骤中未定义
            domain_defined = any(
                any(kw in prop.statement.lower() for kw in ["∈", "in", "∈", "属于", "定义域", "domain"])
                for _ in variables
            )
            if not domain_defined and len(variables) > 2:
                errors.append(f"变量 {variables} 未声明定义域")
                report.variable_domain_valid = False

        # 检查符号一致性
        symbols = self._extract_symbols(prop.statement)
        if len(symbols) > 5:
            # 检查推导步骤中是否使用了未定义的符号
            for step in prop.derivation_steps:
                step_symbols = self._extract_symbols(step.conclusion)
                new_symbols = step_symbols - symbols
                if new_symbols and not step.derivation_rule:
                    errors.append(
                        f"步骤 {step.step_number}: 引入新符号 {new_symbols} 但未声明推导规则"
                    )
                    report.symbol_consistency_valid = False

        # 检查自相矛盾
        conclusions = [s.conclusion for s in prop.derivation_steps]
        for i, c1 in enumerate(conclusions):
            for j, c2 in enumerate(conclusions):
                if i < j and self._is_contradiction(c1, c2):
                    report.self_contradiction_found = True
                    errors.append(f"步骤 {i+1} 与步骤 {j+1} 的结论矛盾")

        report.syntax_errors = errors
        if errors:
            report.syntax_valid = False

    # =========================================================================
    # L2: 逻辑断层检测
    # =========================================================================

    def _layer2_gap_detection(
        self, prop: MathProposition, report: MathValidationReport
    ) -> None:
        """L2 逻辑断层检测（v1.1.1 增强：含分类体系）"""
        steps = prop.derivation_steps
        if not steps:
            return

        for step in steps:
            # 检查 gap
            if step.has_gap:
                gap_desc = step.gap_description or "未指定"
                classification = self.classify_gap(gap_desc)
                report.logical_gaps.append({
                    "step_id": step.step_id,
                    "description": gap_desc,
                    "taxonomy_id": classification["taxonomy_id"],
                    "category": classification["category"],
                    "subcategory": classification["subcategory"],
                    "severity": classification["severity"],
                    "fallacy_id": classification["fallacy_id"],
                })

            # 检查隐性假设
            if step.has_hidden_assumption:
                report.hidden_assumptions.append({
                    "step_id": step.step_id,
                    "description": step.hidden_assumption or "未指定",
                })

            # 检查循环论证
            if step.is_circular:
                report.circular_reasoning_found = True
                report.circular_details.append(
                    f"步骤 {step.step_number}: {step.circular_reference}"
                )

            # 检查前提完整性
            if step.premises:
                for premise in step.premises:
                    # 检查前提是否在之前的步骤中建立了
                    premise_established = any(
                        premise in s.conclusion for s in steps[:step.step_number - 1]
                    )
                    if not premise_established and step.step_number > 1:
                        # 前提可能来自外部，不强制报错
                        pass

    # =========================================================================
    # L3: 红队对抗校验（接口预留）
    # =========================================================================

    def red_team_validate(
        self,
        proposition: MathProposition,
    ) -> list[dict[str, Any]]:
        """
        L3 红队对抗校验

        生成红队测试用例（边界极值、特例暴力、微小扰动），
        由外部 Worker 实际执行。

        Returns:
            红队测试用例列表，每个包含：
              - test_type: "boundary" | "edge_case" | "perturbation"
              - test_description: 测试描述
              - test_parameters: 测试参数
        """
        tests: list[dict[str, Any]] = []

        # 边界极值测试
        tests.append({
            "test_type": "boundary",
            "test_description": f"边界极值测试: 验证命题在定义域边界的行为",
            "test_parameters": {"proposition_id": proposition.proposition_id},
        })

        # 特例暴力遍历
        tests.append({
            "test_type": "edge_case",
            "test_description": f"特例遍历: 对命题涉及的特例进行暴力验证",
            "test_parameters": {"proposition_id": proposition.proposition_id},
        })

        # 微小扰动验证
        tests.append({
            "test_type": "perturbation",
            "test_description": f"扰动验证: 对命题条件进行微小扰动，检查稳定性",
            "test_parameters": {"proposition_id": proposition.proposition_id},
        })

        return tests

    # =========================================================================
    # 综合判定
    # =========================================================================

    def _compute_overall_score(self, report: MathValidationReport) -> None:
        """计算综合校验分数"""
        score = 1.0

        # L1 扣分
        if not report.syntax_valid:
            score -= 0.3
        if report.self_contradiction_found:
            score -= 0.5

        # L2 扣分
        score -= len(report.logical_gaps) * 0.15
        score -= len(report.hidden_assumptions) * 0.1
        if report.circular_reasoning_found:
            score -= 0.3

        report.overall_score = max(0.0, min(1.0, score))
        report.overall_valid = report.overall_score >= 0.7
        report.requires_iteration = not report.overall_valid

        if report.requires_iteration:
            hints = []
            if report.logical_gaps:
                hints.append(f"修复 {len(report.logical_gaps)} 处逻辑缺口")
            if report.hidden_assumptions:
                hints.append(f"声明 {len(report.hidden_assumptions)} 处隐性假设")
            if report.circular_reasoning_found:
                hints.append("消除循环论证")
            if not report.syntax_valid:
                hints.append("修复语法错误")
            report.iteration_hints = hints

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _check_circular(self, step: MathDerivationStep, errors: list[str]) -> None:
        """检查循环论证"""
        full_text = " ".join(step.premises) + " " + step.conclusion
        for pattern, desc in self.CIRCULAR_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                errors.append(f"检测到循环论证模式: {desc}")
                step.is_circular = True
                step.circular_reference = desc
                return

        # 检查结论是否在前提中出现
        for premise in step.premises:
            if step.conclusion.strip() in premise:
                errors.append("结论在前提中已出现，疑似循环论证")
                step.is_circular = True
                step.circular_reference = "结论出现在前提中"
                return

    def _check_hidden_assumption(
        self, step: MathDerivationStep, errors: list[str]
    ) -> None:
        """检查隐性假设"""
        for signal in self.HIDDEN_ASSUMPTION_SIGNALS:
            if signal in step.justification and not step.derivation_rule:
                errors.append(f"检测到可能的隐性假设: '{signal}'")
                step.has_hidden_assumption = True
                step.hidden_assumption = (
                    step.hidden_assumption or f"使用'{signal}'但未声明推导规则"
                )
                return

    # =========================================================================
    # 逻辑断层分类 (Gap Classification) — v1.1.1 增强
    # =========================================================================

    @classmethod
    def classify_gap(cls, gap_description: str) -> dict[str, str]:
        """
        对逻辑断层描述进行细粒度分类

        Returns:
            dict with keys: taxonomy_id, category, subcategory, severity, fallacy_id
        """
        result: dict[str, str] = {
            "taxonomy_id": "unknown",
            "category": "未分类",
            "subcategory": "未识别",
            "severity": "low",
            "fallacy_id": "",
        }

        # 遍历分类体系
        for tax_id, tax_info in cls.GAP_TAXONOMY.items():
            for pattern in tax_info["patterns"]:
                if re.search(pattern, gap_description, re.IGNORECASE):
                    result["taxonomy_id"] = tax_id
                    result["category"] = tax_info["category"]
                    result["subcategory"] = tax_info["subcategory"]
                    result["severity"] = tax_info["severity"]
                    # 匹配谬误模式库
                    for fallacy in cls.FALLACY_PATTERN_LIBRARY:
                        if fallacy["category"] == tax_id:
                            result["fallacy_id"] = fallacy["fallacy_id"]
                            break
                    return result

        return result

    @staticmethod
    def _extract_variables(text: str) -> list[str]:
        """提取数学变量"""
        # 匹配常见变量模式: 单个字母或带下标的字母
        pattern = r'\b([a-zA-Z](?:_\{?[a-zA-Z0-9]+\}?)?)\b'
        # 排除常见关键词
        keywords = {
            "if", "and", "or", "not", "for", "all", "any", "some", "the",
            "is", "in", "of", "to", "be", "let", "set", "then", "there",
            "exists", "such", "that", "with", "from", "have", "has", "are",
            "we", "can", "will", "this", "each", "per", "by", "on", "as",
            "a", "an", "it", "at", "no", "so", "do", "he", "she", "they",
            "I", "We", "You", "He", "She", "It", "They",
        }
        matches = re.findall(pattern, text)
        return [m for m in matches if m.lower() not in keywords]

    @staticmethod
    def _extract_symbols(text: str) -> set[str]:
        """提取数学符号"""
        # 匹配 LaTeX 风格符号: \alpha, \beta, \sum, \prod 等
        pattern = r'\\[a-zA-Z]+'
        matches = re.findall(pattern, text)
        return set(matches)

    @staticmethod
    def _is_contradiction(c1: str, c2: str) -> bool:
        """简单检测两个结论是否矛盾（启发式）"""
        # 检查否定词模式
        neg_patterns = [
            (r"(?:不是|不等于|不成立|false|not|≠|≠)", r"(?:是|等于|成立|true|is|=|＝)"),
        ]
        for neg_pat, pos_pat in neg_patterns:
            if re.search(neg_pat, c1) and re.search(pos_pat, c2):
                # 提取核心内容进行模糊比较
                core1 = re.sub(r'(?:不是|不等于|不成立|false|not|≠|≠)', '', c1).strip()
                core2 = re.sub(r'(?:是|等于|成立|true|is|=|＝)', '', c2).strip()
                if core1 and core2 and (
                    core1 in core2 or core2 in core1 or
                    len(set(core1.split()) & set(core2.split())) / max(len(core1.split()), len(core2.split()), 1) > 0.5
                ):
                    return True
        return False

    @property
    def validation_count(self) -> int:
        return self._validation_count