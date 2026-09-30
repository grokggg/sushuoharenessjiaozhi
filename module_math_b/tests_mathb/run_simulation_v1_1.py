"""
module_math_b.tests_mathb.run_simulation_v1_1 — 真实开放数论子命题仿真探索

基于 v1.1 已完成的 8 场景实测，选取 10 个真实开放数论衍生子命题，
混合不同插件开关组合，覆盖 PROVEN / DISPROVEN / FORCED_TERMINATE 全分支，
收集逻辑断层告警、符号校验结果、停滞分析输出，整理仿真实验数据集。

命题矩阵（10 个场景）：
  ── PROVEN 分支 ──
  Z1  伯特兰公设 (Chebyshev 定理)              PROVEN     sympy
  Z2  威尔逊定理                                PROVEN     无插件
  Z3  卡塔兰猜想 (Mihăilescu 定理)              PROVEN     lean_repl
  ── DISPROVEN 分支 ──
  Z4  费马数猜想 F₅ 反例                        DISPROVEN  sympy
  Z5  n²+n+41 素数猜想 (n=40 反例)              DISPROVEN  无插件
  Z6  "所有素数均形如 6k±1" 反例                 DISPROVEN  sympy+stagnation
  ── FORCED_TERMINATE 分支 ──
  Z7  Collatz 猜想 (3n+1 问题)                  FORCED_TERMINATE  sympy+stagnation
  Z8  Legendre 猜想 (n²与(n+1)²之间的素数)       FORCED_TERMINATE  stagnation
  Z9  奇完全数猜想                               FORCED_TERMINATE  全插件
  ── 混合命题集 ──
  Z10 混合命题集 (PROVEN + DISPROVEN + INCONCLUSIVE)  DISPROVEN  全插件

输出数据集字段：
  - scenario_id, name, expected_branch, actual_branch, rounds
  - logical_gap_count, gap_descriptions
  - symbol_validation_results, syntax_errors
  - stagnation_severity, stagnation_root_causes, stagnation_suggestions
  - plugin_config, plugin_results
  - hash_chain_valid, hash_chain_length
  - proposition_statuses
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
    MathConvergenceReport,
)
from module_math_b.math_hypo_pool import MathHypothesisPool
from module_math_b.math_convergence import MathConvergence
from module_math_b.math_validator import MathValidator
from module_math_b.math_snapshot_bridge import MathSnapshotBridge
from module_math_b.report_exporter import ReportExporter, ReportConfig
from module_math_b.plugins.plugin_registry import (
    PluginRegistry,
    PluginConfig,
    PluginResult,
    PluginStatus,
)
from module_math_b.plugins.sympy_bridge import SympyBridge
from module_math_b.plugins.lean_repl_bridge import LeanReplBridge
from module_math_b.plugins.stagnation_analyzer import StagnationAnalyzer


# =============================================================================
# 输出目录
# =============================================================================

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "simulation_output_v1_1",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def write_file(filename: str, content: str) -> str:
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# =============================================================================
# 仿真数据集结构
# =============================================================================

@dataclass
class SimulationRecord:
    """单场景仿真实验记录"""
    scenario_id: str
    name: str
    expected_branch: str
    actual_branch: str
    total_rounds: int
    hash_chain_valid: bool
    hash_chain_length: int
    passed: bool

    # 命题状态
    propositions: list[dict[str, Any]] = field(default_factory=list)

    # 逻辑断层告警
    logical_gap_count: int = 0
    gap_descriptions: list[str] = field(default_factory=list)
    hidden_assumption_count: int = 0
    circular_count: int = 0

    # 符号校验结果
    syntax_valid: bool = True
    syntax_errors: list[str] = field(default_factory=list)
    self_contradiction_found: bool = False
    variable_domain_valid: bool = True
    symbol_consistency_valid: bool = True

    # 停滞分析输出
    stagnation_severity: str = ""
    stagnation_root_causes: list[str] = field(default_factory=list)
    stagnation_suggestions: list[str] = field(default_factory=list)
    stagnation_rounds: int = 0

    # 插件配置与结果
    plugin_config: dict[str, Any] = field(default_factory=dict)
    plugin_results: dict[str, Any] = field(default_factory=dict)

    # 收敛报告
    convergence_report: dict[str, Any] = field(default_factory=dict)

    # 报告路径
    report_path: str = ""
    error: str = ""


# =============================================================================
# 场景执行引擎
# =============================================================================

def run_simulation_scenario(
    scenario_id: str,
    name: str,
    expected_branch: str,
    propositions_spec: list[dict[str, Any]],
    plugin_config: dict[str, Any],
    max_rounds: int = 5,
) -> SimulationRecord:
    """
    执行单个仿真场景，收集完整数据集。

    与 run_field_test 的差异：
      - 额外收集 L2 逻辑断层告警详情
      - 额外收集 L1 符号校验结果
      - 额外收集 stagnation_analyzer 分析输出
      - 构建结构化数据集
    """
    log(f"  ┌─ {scenario_id}: {name}")
    log(f"  │  预期: {expected_branch} | 插件: {list(plugin_config.get('plugins', {}).keys())}")

    try:
        # 1. 初始化
        pool = MathHypothesisPool()
        validator = MathValidator()
        convergence = MathConvergence()
        bridge = MathSnapshotBridge(task_id=scenario_id)

        # 2. 插件
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))
        registry.register(LeanReplBridge(), PluginConfig(name="lean_repl_bridge", enabled=False))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))
        registry.load_config({"mathb_config": plugin_config})

        # 3. 注册命题
        for ps in propositions_spec:
            pool.register_proposition(
                proposition_id=ps["id"],
                statement=ps["statement"],
                domain=ps.get("domain", "number_theory"),
                difficulty=ps.get("difficulty", "intermediate"),
            )

        # 4. 数据收集器
        all_gap_descriptions: list[str] = []
        all_syntax_errors: list[str] = []
        all_plugin_results: dict[str, list[PluginResult]] = {}
        final_convergence_report: dict[str, Any] = {}
        final_validation_summary: dict[str, Any] = {}

        for round_num in range(1, max_rounds + 1):
            # 4a. 添加推导步骤
            for ps in propositions_spec:
                for s_data in ps.get("derivation_steps", []):
                    if s_data.get("round", 1) != round_num:
                        continue
                    step = MathDerivationStep(
                        step_id=s_data.get("step_id", f"{ps['id']}_s{round_num}"),
                        step_number=s_data.get("step_number", round_num),
                        premises=s_data.get("premises", []),
                        conclusion=s_data.get("conclusion", ""),
                        derivation_rule=s_data.get("rule", ""),
                        justification=s_data.get("justification", ""),
                        has_gap=s_data.get("has_gap", False),
                        gap_description=s_data.get("gap_description", ""),
                        has_hidden_assumption=s_data.get("has_hidden_assumption", False),
                        hidden_assumption=s_data.get("hidden_assumption", ""),
                        is_circular=s_data.get("is_circular", False),
                        circular_reference=s_data.get("circular_reference", ""),
                    )
                    validator.validate_derivation_step(step, [])
                    pool.add_derivation_step(ps["id"], step)
                    # 收集 gap
                    if step.has_gap and step.gap_description:
                        all_gap_descriptions.append(f"[{ps['id']}] {step.gap_description}")

            # 4b. 添加反例
            for ps in propositions_spec:
                for ce_data in ps.get("counter_examples", []):
                    if ce_data.get("round", 1) != round_num:
                        continue
                    ce = MathCounterExample(
                        example_id=ce_data.get("example_id", f"{ps['id']}_ce{round_num}"),
                        target_proposition_id=ps["id"],
                        value_representation=ce_data.get("value", ""),
                        is_valid=ce_data.get("is_valid", True),
                        is_reproducible=ce_data.get("is_reproducible", True),
                    )
                    pool.add_counter_example(ps["id"], ce)

            # 4c. 校验报告 + L1 符号校验
            for ps in propositions_spec:
                for r_data in ps.get("validation_reports", []):
                    if r_data.get("round", 1) != round_num:
                        continue
                    vr = MathValidationReport(
                        report_id=r_data.get("report_id", f"{ps['id']}_vr{round_num}"),
                        proposition_id=ps["id"],
                        overall_score=r_data.get("overall_score", 0.5),
                        overall_valid=r_data.get("overall_valid", False),
                        round_number=round_num,
                        syntax_valid=r_data.get("syntax_valid", True),
                        syntax_errors=r_data.get("syntax_errors", []),
                        self_contradiction_found=r_data.get("self_contradiction_found", False),
                        variable_domain_valid=r_data.get("variable_domain_valid", True),
                        symbol_consistency_valid=r_data.get("symbol_consistency_valid", True),
                    )
                    pool.add_validation_report(ps["id"], vr)
                    all_syntax_errors.extend(r_data.get("syntax_errors", []))

            # 4d. 更新状态
            pool.update_statuses_from_validation()

            # 4e. 执行插件
            props = pool.get_all_propositions()
            plugin_context = {
                "query": name,
                "round_number": round_num,
                "propositions": [
                    {"proposition_id": p.proposition_id, "statement": p.statement, "status": p.status}
                    for p in props
                ],
                "derivation_steps": [
                    {
                        "step_id": sd.get("step_id", ""),
                        "proposition_id": ps_data["id"],
                        "step_number": sd.get("step_number", 1),
                        "has_gap": sd.get("has_gap", False),
                        "gap_description": sd.get("gap_description", ""),
                    }
                    for ps_data in propositions_spec
                    for sd in ps_data.get("derivation_steps", [])
                    if sd.get("round", 1) <= round_num
                ],
                "validation_reports": [
                    {"proposition_id": ps_data["id"], "overall_score": r.get("overall_score", 0)}
                    for ps_data in propositions_spec
                    for r in ps_data.get("validation_reports", [])
                    if r.get("round", 1) <= round_num
                ],
                "stagnation_rounds": convergence.stagnation_rounds,
            }
            round_results = registry.execute_enabled(plugin_context)
            for name, res in round_results.items():
                if name not in all_plugin_results:
                    all_plugin_results[name] = []
                all_plugin_results[name].append(res)

            # 4f. 收敛判定
            cr = convergence.evaluate(pool, round_num)
            final_convergence_report = {
                "is_converged": cr.is_converged,
                "convergence_type": cr.convergence_type,
                "convergence_reason": cr.convergence_reason,
                "proof_completeness": cr.proof_completeness,
                "proof_gap_count": cr.proof_gap_count,
                "proof_circular_count": cr.proof_circular_count,
                "proof_hidden_assumption_count": cr.proof_hidden_assumption_count,
                "stagnation_rounds": cr.stagnation_rounds,
            }

            # 4g. 快照
            validation_summary = {
                "total_validations": round_num,
                "pass_rate": 0.5,
                "logical_gaps": len(all_gap_descriptions),
                "hidden_assumptions": cr.proof_hidden_assumption_count,
                "circular_count": cr.proof_circular_count,
                "self_contradiction_count": 0,
                "boundary_tests_passed": 0,
            }
            bridge.create_snapshot(
                round_number=round_num,
                pool=pool,
                convergence_report=cr,
                validation_summary=validation_summary,
            )
            final_validation_summary = validation_summary

            if cr.is_converged:
                break

        # 5. 汇总
        final_props = pool.to_dict_list()
        actual_branch = final_convergence_report.get("convergence_type", "PENDING")
        hash_chain_valid = bridge.verify_chain_integrity()
        hash_chain_length = len(bridge.get_all_snapshots())
        branch_match = actual_branch == expected_branch

        # 6. 提取停滞分析输出
        stag_severity = ""
        stag_causes: list[str] = []
        stag_suggestions: list[str] = []
        if "stagnation_analyzer" in all_plugin_results:
            for result in all_plugin_results["stagnation_analyzer"]:
                if result.status == PluginStatus.ENABLED and result.output:
                    diag = result.output.get("diagnosis", {})
                    stag_severity = diag.get("severity", "")
                    stag_causes = diag.get("root_causes", [])
                    stag_suggestions = diag.get("suggestions", [])

        # 7. 汇总插件结果
        last_plugin_results: dict[str, Any] = {}
        for pname, results in all_plugin_results.items():
            if results:
                last = results[-1]
                last_plugin_results[pname] = {
                    "plugin_name": last.plugin_name,
                    "status": last.status.value,
                    "output": last.output,
                    "error": last.error,
                    "elapsed_ms": last.elapsed_ms,
                }

        # 8. 导出报告
        exporter = ReportExporter(
            bridge,
            plugin_results={
                pname: PluginResult(
                    plugin_name=last.plugin_name,
                    status=last.status,
                    output=last.output,
                    error=last.error,
                    elapsed_ms=last.elapsed_ms,
                )
                for pname, rlist in all_plugin_results.items() if rlist
                for last in [rlist[-1]]
            },
        )
        report_md = exporter.export_to_markdown()
        report_path = write_file(f"{scenario_id}_report.md", report_md)
        report_json = exporter.export_to_json()
        write_file(f"{scenario_id}_report.json", json.dumps(report_json, ensure_ascii=False, indent=2))

        # 9. 构建记录
        record = SimulationRecord(
            scenario_id=scenario_id,
            name=name,
            expected_branch=expected_branch,
            actual_branch=actual_branch,
            total_rounds=hash_chain_length,
            hash_chain_valid=hash_chain_valid,
            hash_chain_length=hash_chain_length,
            passed=branch_match and hash_chain_valid,
            propositions=final_props,
            logical_gap_count=len(all_gap_descriptions),
            gap_descriptions=all_gap_descriptions,
            hidden_assumption_count=final_convergence_report.get("proof_hidden_assumption_count", 0),
            circular_count=final_convergence_report.get("proof_circular_count", 0),
            syntax_errors=all_syntax_errors,
            stagnation_severity=stag_severity,
            stagnation_root_causes=stag_causes,
            stagnation_suggestions=stag_suggestions,
            stagnation_rounds=final_convergence_report.get("stagnation_rounds", 0),
            plugin_config=plugin_config,
            plugin_results=last_plugin_results,
            convergence_report=final_convergence_report,
            report_path=report_path,
        )

        log(f"  │  实际: {actual_branch} | 轮次: {hash_chain_length} | 缺口: {len(all_gap_descriptions)}")
        log(f"  │  停滞: {stag_severity} | 哈希链: {'✅' if hash_chain_valid else '❌'}")
        log(f"  └─ {'✅ 通过' if record.passed else '❌ 失败'}")

        return record

    except Exception as e:
        log(f"  └─ ❌ 异常: {e}")
        traceback.print_exc()
        return SimulationRecord(
            scenario_id=scenario_id, name=name,
            expected_branch=expected_branch, actual_branch="ERROR",
            total_rounds=0, hash_chain_valid=False, hash_chain_length=0,
            passed=False, error=str(e),
        )


# =============================================================================
# 场景定义
# =============================================================================

# ── Z1: 伯特兰公设 (PROVEN + sympy) ──
Z1_BERTRAND = {
    "id": "Z1",
    "name": "伯特兰公设 (Chebyshev 定理): 对任意 n>1，存在素数 p 满足 n<p<2n",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p1", "statement": "对任意整数 n>1，存在素数 p 满足 n < p < 2n",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p1_s1", "step_number": 1,
                    "premises": ["Chebyshev 定理 (1850): π(x) ~ x/log x"],
                    "conclusion": "θ(x) = Σ_{p≤x} log p 满足 θ(x) ≥ x/3 log x (x≥2)",
                    "rule": "theorem", "justification": "Chebyshev 界",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p1_s2", "step_number": 2,
                    "premises": ["θ(2n) - θ(n) > 0 对所有 n>1 成立"],
                    "conclusion": "在 (n, 2n] 中至少存在一个素数",
                    "rule": "inequality",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p1_vr1",
                    "overall_score": 1.0, "overall_valid": True,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z2: 威尔逊定理 (PROVEN，无插件) ──
Z2_WILSON = {
    "id": "Z2",
    "name": "威尔逊定理: n 是素数当且仅当 (n-1)! ≡ -1 (mod n)",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p2", "statement": "n 是素数当且仅当 (n-1)! ≡ -1 (mod n)",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p2_s1", "step_number": 1,
                    "premises": ["若 n 是素数，则 Z_n 是域，其乘法群 Z_n* 是循环群"],
                    "conclusion": "Z_n* 中所有元素的乘积 ≡ -1 (mod n)",
                    "rule": "group_theory",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p2_s2", "step_number": 2,
                    "premises": ["Z_n* = {1, 2, ..., n-1}"],
                    "conclusion": "(n-1)! ≡ -1 (mod n) 当 n 为素数",
                    "rule": "algebraic_manipulation",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p2_s3", "step_number": 3,
                    "premises": ["若 n 是合数，则存在 d | n 且 1 < d < n"],
                    "conclusion": "d 整除 (n-1)!，故 (n-1)! ≡ 0 (mod d) 不满足 ≡ -1，逆命题成立",
                    "rule": "contrapositive",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p2_vr1",
                    "overall_score": 1.0, "overall_valid": True,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {"plugins": {}},
}

# ── Z3: 卡塔兰猜想 (PROVEN + lean_repl) ──
Z3_CATALAN = {
    "id": "Z3",
    "name": "卡塔兰猜想 (Mihăilescu 定理): 3²-2³=1 是唯一解",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p3", "statement": "方程 x^a - y^b = 1 的正整数解 (x,a,y,b>1) 仅有 (3,2,2,3)",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p3_s1", "step_number": 1,
                    "premises": ["Mihăilescu 定理 (2002): 利用分圆域和 Galois 表示"],
                    "conclusion": "x^a - y^b = 1 仅当 {x^a, y^b} = {3², 2³} 时成立",
                    "rule": "theorem",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p3_s2", "step_number": 2,
                    "premises": ["3² = 9, 2³ = 8, 9-8 = 1"],
                    "conclusion": "验证唯一解 3² - 2³ = 1 确实满足方程",
                    "rule": "computation",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p3_vr1",
                    "overall_score": 1.0, "overall_valid": True,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30},
        }
    },
}

# ── Z4: 费马数猜想反例 F₅ (DISPROVEN + sympy) ──
Z4_FERMAT_DISPROVEN = {
    "id": "Z4",
    "name": "费马数猜想: 所有 F_n = 2^(2^n)+1 都是素数 → F₅ 反例",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p4", "statement": "所有费马数 F_n = 2^(2^n) + 1 都是素数",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p4_s1", "step_number": 1,
                    "premises": ["F₀=3, F₁=5, F₂=17, F₃=257, F₄=65537 均为素数"],
                    "conclusion": "前 5 个费马数均为素数，费马猜想所有 F_n 为素数",
                    "rule": "empirical_induction",
                    "has_gap": True, "gap_description": "仅凭有限特例归纳，无法推广到全体",
                    "has_hidden_assumption": True, "hidden_assumption": "假设后续费马数遵循相同模式",
                    "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p4_s2", "step_number": 2,
                    "premises": ["Euler (1732): F₅ = 2^32 + 1 = 4294967297 = 641 × 6700417"],
                    "conclusion": "F₅ 是合数，原猜想被证伪",
                    "rule": "counterexample",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p4_ce1",
                    "value": "F₅ = 2^32+1 = 4294967297 = 641 × 6700417",
                    "is_valid": True, "is_reproducible": True,
                }
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p4_vr1",
                    "overall_score": 0.55, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z5: n²+n+41 素数猜想 (DISPROVEN，无插件) ──
Z5_EULER_POLYNOMIAL_DISPROVEN = {
    "id": "Z5",
    "name": "Euler 多项式素数猜想: n²+n+41 对所有自然数 n 都是素数",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p5", "statement": "n² + n + 41 对所有自然数 n 都是素数",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p5_s1", "step_number": 1,
                    "premises": ["n=0→41, n=1→43, ..., n=39→1601 均为素数"],
                    "conclusion": "前 40 个值均为素数，Euler 注意到此模式",
                    "rule": "computation",
                    "has_gap": True, "gap_description": "仅凭 40 个特例归纳，需要一般性证明",
                    "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p5_s2", "step_number": 2,
                    "premises": ["n=40: 40²+40+41 = 1681 = 41²"],
                    "conclusion": "n=40 时多项式值为合数，原猜想被证伪",
                    "rule": "counterexample",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p5_ce1",
                    "value": "n=40: 40²+40+41 = 1681 = 41²",
                    "is_valid": True, "is_reproducible": True,
                },
                {
                    "round": 1, "example_id": "p5_ce2",
                    "value": "n=41: 41²+41+41 = 41(41+1+1) = 41×43 = 1763",
                    "is_valid": True, "is_reproducible": True,
                },
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p5_vr1",
                    "overall_score": 0.5, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [
                        "推导步骤 p5_s1 存在跳步信号词: '仅凭特例归纳'"
                    ],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {"plugins": {}},
}

# ── Z6: "所有素数均形如 6k±1" (DISPROVEN + sympy+stagnation) ──
Z6_PRIME_FORM_DISPROVEN = {
    "id": "Z6",
    "name": "素数形式猜想: 所有大于3的素数均形如 6k±1（反例: 2和3）",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p6", "statement": "所有素数均形如 6k±1（即 6k+1 或 6k-1）",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p6_s1", "step_number": 1,
                    "premises": ["模6剩余类: 0,1,2,3,4,5 → 6k,6k+1,6k+2,6k+3,6k+4,6k+5"],
                    "conclusion": "6k 是6的倍数 (合数), 6k+2 是偶数 (k>0时), 6k+3 是3的倍数, 6k+4 是偶数",
                    "rule": "divisibility",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p6_s2", "step_number": 2,
                    "premises": ["大于3的素数不能是 6k, 6k+2, 6k+3, 6k+4"],
                    "conclusion": "大于3的素数只能形如 6k+1 或 6k+5 (即 6k-1)",
                    "rule": "case_analysis",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p6_s3", "step_number": 3,
                    "premises": ["命题声称'所有素数'均形如 6k±1"],
                    "conclusion": "但 2 和 3 是素数，且 2=6×0+2, 3=6×0+3，不满足 6k±1",
                    "rule": "counterexample",
                    "has_gap": True, "gap_description": "命题未排除 n=2,3 的边界情况，陈述不严谨",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p6_ce1",
                    "value": "2 = 6×0+2，不满足 6k±1",
                    "is_valid": True, "is_reproducible": True,
                },
                {
                    "round": 1, "example_id": "p6_ce2",
                    "value": "3 = 6×0+3，不满足 6k±1",
                    "is_valid": True, "is_reproducible": True,
                },
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p6_vr1",
                    "overall_score": 0.6, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z7: Collatz 猜想 (FORCED_TERMINATE + sympy+stagnation) ──
Z7_COLLATZ_INCONCLUSIVE = {
    "id": "Z7",
    "name": "Collatz 猜想 (3n+1 问题): 所有正整数最终到达 1",
    "expected_branch": "FORCED_TERMINATE",
    "propositions": [
        {
            "id": "p7", "statement": "对任意正整数 n，Collatz 序列 n→n/2 (偶) 或 3n+1 (奇) 最终必到达 1",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p7_s1", "step_number": 1,
                    "premises": ["已验证到 2^68 ≈ 2.95×10^20 均成立"],
                    "conclusion": "猜想在已有范围内成立，但无一般证明",
                    "rule": "empirical_verification",
                    "has_gap": True, "gap_description": "有限验证不能代替无限证明，存在非平凡循环或发散的可能",
                    "has_hidden_assumption": True, "hidden_assumption": "假设所有正整数行为一致，无例外",
                    "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p7_s2", "step_number": 2,
                    "premises": ["Terence Tao (2019): 几乎所有 n 满足 Collatz 猜想"],
                    "conclusion": "对数密度趋近于 1，但不排除零测度反例",
                    "rule": "theorem",
                    "has_gap": True, "gap_description": "'几乎所有'不等于'所有'，零测度反例可能仍存在",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p7_vr1",
                    "overall_score": 0.15, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z8: Legendre 猜想 (FORCED_TERMINATE + stagnation) ──
Z8_LEGENDRE_INCONCLUSIVE = {
    "id": "Z8",
    "name": "Legendre 猜想: n² 与 (n+1)² 之间总存在素数",
    "expected_branch": "FORCED_TERMINATE",
    "propositions": [
        {
            "id": "p8", "statement": "对任意正整数 n，在 n² 与 (n+1)² 之间至少存在一个素数",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p8_s1", "step_number": 1,
                    "premises": ["素数定理: π(x) ~ x/log x，区间 (n², (n+1)²) 长度 ≈ 2n"],
                    "conclusion": "期望素数个数 ≈ 2n / log(n²) = n / log n → ∞，但并非严格证明",
                    "rule": "asymptotic_analysis",
                    "has_gap": True, "gap_description": "概率期望≠确定性存在，素数分布可能存在局部异常",
                    "has_hidden_assumption": True, "hidden_assumption": "假设素数在区间内均匀分布",
                    "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p8_s2", "step_number": 2,
                    "premises": ["Oppermann 猜想 (更强的猜想): n²-n 与 n² 之间、n² 与 n²+n 之间均有素数"],
                    "conclusion": "若 Oppermann 猜想成立，则 Legendre 猜想自动成立，但 Oppermann 也未证明",
                    "rule": "implication",
                    "has_gap": True, "gap_description": "依赖更强但同样未证明的猜想，循环依赖",
                    "has_hidden_assumption": False, "is_circular": True, "circular_reference": "用未证明的更强的猜想推导较弱的猜想",
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p8_vr1",
                    "overall_score": 0.1, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [
                        "推导步骤 p8_s2 存在循环论证: 依赖未证明的更强猜想"
                    ],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z9: 奇完全数猜想 (FORCED_TERMINATE + 全插件) ──
Z9_ODD_PERFECT_INCONCLUSIVE = {
    "id": "Z9",
    "name": "奇完全数猜想: 是否存在奇完全数?",
    "expected_branch": "FORCED_TERMINATE",
    "propositions": [
        {
            "id": "p9a", "statement": "不存在奇完全数",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p9a_s1", "step_number": 1,
                    "premises": ["若奇完全数存在，则至少有 9 个不同的素因子 (Nielsen 2006)"],
                    "conclusion": "奇完全数若存在，必须极其巨大 (> 10^1500)",
                    "rule": "bound",
                    "has_gap": True, "gap_description": "下界不断提高，但无法排除存在性",
                    "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p9a_s2", "step_number": 2,
                    "premises": ["Ochem & Rao (2012): 奇完全数 > 10^1500"],
                    "conclusion": "搜索范围已极大，但无法穷举",
                    "rule": "computation",
                    "has_gap": True, "gap_description": "有限搜索不等于证明了不存在性",
                    "has_hidden_assumption": True, "hidden_assumption": "假设超大数范围内不存在反例",
                    "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p9a_vr1",
                    "overall_score": 0.1, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        },
        {
            "id": "p9b", "statement": "奇完全数若存在，σ(n)=2n，且 n 为奇数",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p9b_s1", "step_number": 1,
                    "premises": ["σ(n) = 2n 是完全数的定义"],
                    "conclusion": "若 n 为奇数且 σ(n)=2n，则 n 为奇完全数",
                    "rule": "by_definition",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p9b_vr1",
                    "overall_score": 0.8, "overall_valid": True,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        },
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── Z10: 混合命题集 (PROVEN + DISPROVEN + INCONCLUSIVE，全插件) ──
Z10_MIXED_SET = {
    "id": "Z10",
    "name": "混合命题集: 威尔逊定理(已证) + 费马数(反例) + 奇完全数(开放)",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p10a", "statement": "威尔逊定理: n 是素数 iff (n-1)! ≡ -1 (mod n)",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p10a_s1", "step_number": 1,
                    "premises": ["若 n 素数，Z_n* 是循环群"],
                    "conclusion": "∏_{a∈Z_n*} a ≡ -1 (mod n) → (n-1)! ≡ -1 (mod n)",
                    "rule": "group_theory",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p10a_vr1",
                    "overall_score": 1.0, "overall_valid": True,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        },
        {
            "id": "p10b", "statement": "所有费马数 F_n = 2^(2^n)+1 都是素数",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p10b_s1", "step_number": 1,
                    "premises": ["F₀~F₄ 均为素数"],
                    "conclusion": "费马猜测所有费马数为素数",
                    "rule": "empirical_induction",
                    "has_gap": True, "gap_description": "仅凭前5个特例归纳，Euler 发现 F₅=641×6700417",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p10b_ce1",
                    "value": "F₅ = 4294967297 = 641 × 6700417",
                    "is_valid": True, "is_reproducible": True,
                }
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p10b_vr1",
                    "overall_score": 0.3, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        },
        {
            "id": "p10c", "statement": "不存在奇完全数",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p10c_s1", "step_number": 1,
                    "premises": ["已知条件: 奇完全数若存在 > 10^1500"],
                    "conclusion": "搜索范围极大，无法穷举，无法判定",
                    "rule": "bound",
                    "has_gap": True, "gap_description": "有限搜索无法证明不存在性",
                    "has_hidden_assumption": True, "hidden_assumption": "假设超大数范围内不存在反例",
                    "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p10c_vr1",
                    "overall_score": 0.1, "overall_valid": False,
                    "syntax_valid": True, "syntax_errors": [],
                    "self_contradiction_found": False,
                    "variable_domain_valid": True, "symbol_consistency_valid": True,
                }
            ],
        },
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}


# =============================================================================
# 数据集导出
# =============================================================================

def export_dataset(records: list[SimulationRecord]) -> tuple[str, str]:
    """导出仿真实验数据集 (JSON + CSV 格式)"""

    # JSON 数据集
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.1.0",
        "description": "Module-MathB v1.1 真实开放数论子命题仿真实验数据集",
        "total_scenarios": len(records),
        "passed": sum(1 for r in records if r.passed),
        "branch_coverage": {
            "PROVEN": sum(1 for r in records if r.actual_branch == "PROVEN"),
            "DISPROVEN": sum(1 for r in records if r.actual_branch == "DISPROVEN"),
            "FORCED_TERMINATE": sum(1 for r in records if r.actual_branch == "FORCED_TERMINATE"),
        },
        "records": [asdict(r) for r in records],
    }
    json_path = write_file("simulation_dataset.json", json.dumps(dataset, ensure_ascii=False, indent=2))

    # CSV 数据集（扁平化关键字段）
    csv_lines = [
        "scenario_id,name,expected_branch,actual_branch,total_rounds,hash_chain_valid,"
        "passed,logical_gap_count,hidden_assumption_count,circular_count,"
        "stagnation_severity,stagnation_rounds,proposition_count,"
        "proven_count,disproven_count,inconclusive_count,"
        "sympy_enabled,lean_enabled,stagnation_enabled,"
        "sympy_status,lean_status,stagnation_status"
    ]
    for r in records:
        props = r.propositions
        proven = sum(1 for p in props if p.get("status") == "PROVEN")
        disproven = sum(1 for p in props if p.get("status") == "DISPROVEN")
        inconclusive = sum(1 for p in props if p.get("status") in ("INCONCLUSIVE", "PENDING"))
        plugins = r.plugin_config.get("plugins", {})
        pr = r.plugin_results
        csv_lines.append(
            f"{r.scenario_id},{r.name[:50]},{r.expected_branch},{r.actual_branch},"
            f"{r.total_rounds},{r.hash_chain_valid},{r.passed},"
            f"{r.logical_gap_count},{r.hidden_assumption_count},{r.circular_count},"
            f"{r.stagnation_severity},{r.stagnation_rounds},{len(props)},"
            f"{proven},{disproven},{inconclusive},"
            f"{'sympy_bridge' in plugins},{'lean_repl_bridge' in plugins},{'stagnation_analyzer' in plugins},"
            f"{pr.get('sympy_bridge', {}).get('status', '')},"
            f"{pr.get('lean_repl_bridge', {}).get('status', '')},"
            f"{pr.get('stagnation_analyzer', {}).get('status', '')}"
        )
    csv_path = write_file("simulation_dataset.csv", "\n".join(csv_lines))

    return json_path, csv_path


# =============================================================================
# 主入口
# =============================================================================

def main():
    log("=" * 70)
    log("Module-MathB v1.1 真实开放数论子命题仿真探索")
    log(f"输出目录: {OUTPUT_DIR}")
    log("=" * 70)

    scenarios = [
        Z1_BERTRAND,
        Z2_WILSON,
        Z3_CATALAN,
        Z4_FERMAT_DISPROVEN,
        Z5_EULER_POLYNOMIAL_DISPROVEN,
        Z6_PRIME_FORM_DISPROVEN,
        Z7_COLLATZ_INCONCLUSIVE,
        Z8_LEGENDRE_INCONCLUSIVE,
        Z9_ODD_PERFECT_INCONCLUSIVE,
        Z10_MIXED_SET,
    ]

    records: list[SimulationRecord] = []

    for sc in scenarios:
        log("")
        record = run_simulation_scenario(
            scenario_id=sc["id"],
            name=sc["name"],
            expected_branch=sc["expected_branch"],
            propositions_spec=sc["propositions"],
            plugin_config=sc["plugin_config"],
            max_rounds=5,
        )
        records.append(record)

    # ── 汇总 ──
    log("")
    log("=" * 70)
    log("仿真探索汇总")
    log("=" * 70)

    passed = sum(1 for r in records if r.passed)
    total = len(records)
    branch_counts = {"PROVEN": 0, "DISPROVEN": 0, "FORCED_TERMINATE": 0, "ERROR": 0}
    for r in records:
        branch_counts[r.actual_branch] = branch_counts.get(r.actual_branch, 0) + 1

    log(f"通过: {passed}/{total}")
    log(f"分支覆盖: {branch_counts}")
    all_hash_ok = all(r.hash_chain_valid for r in records if not r.error)
    log(f"哈希链: {'全部通过' if all_hash_ok else '存在异常'}")

    # 详细表
    log("")
    log(f"{'ID':<5} {'场景':<42} {'预期':<18} {'实际':<18} {'轮':<3} {'链':<4} {'缺口':<3} {'停滞':<8} {'结果':<6}")
    log("-" * 115)
    for r in records:
        chain = "✅" if r.hash_chain_valid else "❌"
        status = "✅" if r.passed else "❌"
        stag = r.stagnation_severity[:7] if r.stagnation_severity else "—"
        log(f"{r.scenario_id:<5} {r.name[:40]:<42} {r.expected_branch:<18} {r.actual_branch:<18} "
            f"{r.total_rounds:<3} {chain:<4} {r.logical_gap_count:<3} {stag:<8} {status:<6}")

    # 导出数据集
    log("")
    json_path, csv_path = export_dataset(records)
    log(f"数据集 JSON: {json_path}")
    log(f"数据集 CSV:  {csv_path}")

    # 生成汇总报告
    summary_lines = [f"# Module-MathB v1.1 仿真探索报告",
                     f"",
                     f"> **生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                     f"> **场景总数**: {total} | **通过**: {passed}/{total}",
                     f"",
                     f"---",
                     f"",
                     f"## 分支覆盖",
                     f"",
                     f"| 分支 | 场景数 |",
                     f"|------|--------|"]
    for branch, count in branch_counts.items():
        if count > 0:
            summary_lines.append(f"| {branch} | {count} |")
    summary_lines.append("")
    summary_lines.append("## 场景详情")
    summary_lines.append("")
    summary_lines.append("| ID | 场景 | 预期 | 实际 | 轮次 | 缺口 | 停滞 | 哈希链 | 结果 |")
    summary_lines.append("|----|------|------|------|------|------|------|--------|------|")
    for r in records:
        chain = "✅" if r.hash_chain_valid else "❌"
        status = "✅" if r.passed else "❌"
        stag = r.stagnation_severity or "—"
        summary_lines.append(
            f"| {r.scenario_id} | {r.name[:35]} | {r.expected_branch} | {r.actual_branch} "
            f"| {r.total_rounds} | {r.logical_gap_count} | {stag} | {chain} | {status} |"
        )
    summary_lines.append("")

    # 逻辑断层告警汇总
    summary_lines.append("## 逻辑断层告警汇总")
    summary_lines.append("")
    all_gaps: list[tuple[str, str]] = []
    for r in records:
        for gap in r.gap_descriptions:
            all_gaps.append((r.scenario_id, gap))
    if all_gaps:
        summary_lines.append("| 场景 | 缺口描述 |")
        summary_lines.append("|------|----------|")
        for sid, gap in all_gaps:
            summary_lines.append(f"| {sid} | {gap[:80]} |")
    else:
        summary_lines.append("*无逻辑断层告警*")
    summary_lines.append("")

    # 停滞分析汇总
    summary_lines.append("## 停滞分析汇总")
    summary_lines.append("")
    for r in records:
        if r.stagnation_root_causes:
            summary_lines.append(f"### {r.scenario_id}: {r.name}")
            summary_lines.append(f"- **严重性**: {r.stagnation_severity}")
            summary_lines.append(f"- **根因**: {'; '.join(r.stagnation_root_causes)}")
            if r.stagnation_suggestions:
                summary_lines.append(f"- **建议**: {'; '.join(r.stagnation_suggestions)}")
            summary_lines.append("")
    if not any(r.stagnation_root_causes for r in records):
        summary_lines.append("*无停滞分析输出*")
        summary_lines.append("")

    # 各场景详细报告
    for r in records:
        summary_lines.append(f"---")
        summary_lines.append(f"")
        summary_lines.append(f"## {r.scenario_id}: {r.name}")
        summary_lines.append(f"")
        summary_lines.append(f"- **预期分支**: {r.expected_branch} | **实际**: {r.actual_branch} | **轮次**: {r.total_rounds}")
        summary_lines.append(f"- **哈希链**: {'✅' if r.hash_chain_valid else '❌'} | **通过**: {'✅' if r.passed else '❌'}")
        if r.error:
            summary_lines.append(f"- **错误**: {r.error}")
        summary_lines.append("")
        summary_lines.append(f"### 命题状态")
        for p in r.propositions:
            summary_lines.append(f"- `{p['proposition_id']}`: **{p['status']}** — {p['statement'][:60]}")
        summary_lines.append("")
        summary_lines.append(f"### 逻辑断层")
        summary_lines.append(f"- 缺口数: {r.logical_gap_count}")
        summary_lines.append(f"- 隐性假设: {r.hidden_assumption_count}")
        summary_lines.append(f"- 循环论证: {r.circular_count}")
        if r.gap_descriptions:
            for gap in r.gap_descriptions:
                summary_lines.append(f"  - ⚠️ {gap}")
        summary_lines.append("")
        if r.stagnation_severity:
            summary_lines.append(f"### 停滞分析")
            summary_lines.append(f"- 严重性: {r.stagnation_severity}")
            summary_lines.append(f"- 根因: {'; '.join(r.stagnation_root_causes)}")
            if r.stagnation_suggestions:
                summary_lines.append(f"- 建议: {'; '.join(r.stagnation_suggestions)}")
            summary_lines.append("")
        if r.plugin_results:
            summary_lines.append(f"### 插件结果")
            for pname, pr in r.plugin_results.items():
                summary_lines.append(f"- `{pname}`: {pr.get('status')} ({pr.get('elapsed_ms', 0):.1f}ms)")
            summary_lines.append("")

    summary_md = "\n".join(summary_lines)
    write_file("SIMULATION_SUMMARY.md", summary_md)
    log(f"汇总报告: {OUTPUT_DIR}/SIMULATION_SUMMARY.md")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)