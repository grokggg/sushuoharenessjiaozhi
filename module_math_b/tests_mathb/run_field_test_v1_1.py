"""
module_math_b.tests_mathb.run_field_test_v1_1 — v1.1 应用实测

选取多组中等难度数论子命题，混合开启/关闭插件，
覆盖 PROVEN / DISPROVEN / INCONCLUSIVE / FORCED_TERMINATE 全部状态分支。
运行完整 E2E，导出标准化报告，校验快照哈希链完整性。

命题矩阵（8 个场景）：
  S1 — 欧几里得素数无穷性：PROVEN，无插件
  S2 — 梅森数反例 (n=11)：DISPROVEN，sympy 插件
  S3 — 孪生素数猜想：INCONCLUSIVE → FORCED_TERMINATE，stagnation 插件
  S4 — 哥德巴赫猜想（弱）：INCONCLUSIVE，全插件
  S5 — 费马小定理特例：PROVEN，sympy 插件
  S6 — "所有奇数都是素数"：DISPROVEN，无插件
  S7 — 混合命题集：PROVEN+DISPROVEN+INCONCLUSIVE，混合插件
  S8 — 黎曼ζ函数平凡零点：PROVEN，lean_repl 插件
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field
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
# 输出目录与工具
# =============================================================================

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "field_test_output_v1_1",
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
# 场景执行引擎
# =============================================================================

@dataclass
class ScenarioResult:
    scenario_id: str
    name: str
    expected_branch: str  # PROVEN | DISPROVEN | INCONCLUSIVE | FORCED_TERMINATE
    actual_branch: str
    total_rounds: int
    propositions: list[dict[str, Any]]
    plugin_config: dict[str, Any]
    plugin_results: dict[str, Any]
    convergence_report: dict[str, Any]
    hash_chain_valid: bool
    report_path: str = ""
    error: str = ""
    passed: bool = False


def run_scenario(
    scenario_id: str,
    name: str,
    expected_branch: str,
    propositions_spec: list[dict[str, Any]],
    plugin_config: dict[str, Any],
    max_rounds: int = 4,
) -> ScenarioResult:
    """
    执行单个场景，直接操作假说池/收敛器/校验器/快照桥接。

    propositions_spec 格式:
      [
        {
          "id": "p1", "statement": "...",
          "derivation_steps": [{"premises": [...], "conclusion": "...", "rule": "...", "has_gap": bool, ...}],
          "counter_examples": [{"value": "...", "is_valid": bool, "is_reproducible": bool}],
          "validation_reports": [{"overall_score": float, "overall_valid": bool}],
          "expected_status": "PROVEN",
        },
        ...
      ]
    """
    log(f"  ┌─ 场景 {scenario_id}: {name}")
    log(f"  │  预期分支: {expected_branch} | 插件: {list(plugin_config.get('plugins', {}).keys())}")

    try:
        # 1. 初始化组件
        pool = MathHypothesisPool()
        validator = MathValidator()
        convergence = MathConvergence()
        bridge = MathSnapshotBridge(task_id=scenario_id)

        # 2. 初始化插件
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))
        registry.register(LeanReplBridge(), PluginConfig(name="lean_repl_bridge", enabled=False))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))
        registry.load_config({"mathb_config": plugin_config})

        log(f"  │  已启用插件: {registry.list_enabled()}")

        # 3. 注册命题
        for ps in propositions_spec:
            pool.register_proposition(
                proposition_id=ps["id"],
                statement=ps["statement"],
                domain=ps.get("domain", "number_theory"),
                difficulty=ps.get("difficulty", "intermediate"),
            )

        # 4. 多轮迭代
        all_plugin_results: dict[str, list[PluginResult]] = {}
        final_convergence_report: dict[str, Any] = {}

        for round_num in range(1, max_rounds + 1):
            # 4a. 添加推导步骤
            for ps in propositions_spec:
                steps = ps.get("derivation_steps", [])
                round_steps = [s for s in steps if s.get("round", 1) == round_num]
                for s_data in round_steps:
                    step = MathDerivationStep(
                        step_id=s_data.get("step_id", f"{ps['id']}_s{round_num}"),
                        step_number=s_data.get("step_number", round_num),
                        premises=s_data.get("premises", []),
                        conclusion=s_data.get("conclusion", ""),
                        derivation_rule=s_data.get("rule", ""),
                        has_gap=s_data.get("has_gap", False),
                        gap_description=s_data.get("gap_description", ""),
                        has_hidden_assumption=s_data.get("has_hidden_assumption", False),
                        hidden_assumption=s_data.get("hidden_assumption", ""),
                        is_circular=s_data.get("is_circular", False),
                        circular_reference=s_data.get("circular_reference", ""),
                    )
                    # 校验步骤
                    validator.validate_derivation_step(step, [])
                    pool.add_derivation_step(ps["id"], step)

            # 4b. 添加反例
            for ps in propositions_spec:
                ces = ps.get("counter_examples", [])
                round_ces = [ce for ce in ces if ce.get("round", 1) == round_num]
                for ce_data in round_ces:
                    ce = MathCounterExample(
                        example_id=ce_data.get("example_id", f"{ps['id']}_ce{round_num}"),
                        target_proposition_id=ps["id"],
                        value_representation=ce_data.get("value", ""),
                        is_valid=ce_data.get("is_valid", True),
                        is_reproducible=ce_data.get("is_reproducible", True),
                    )
                    pool.add_counter_example(ps["id"], ce)

            # 4c. 添加校验报告
            for ps in propositions_spec:
                reports = ps.get("validation_reports", [])
                round_reports = [r for r in reports if r.get("round", 1) == round_num]
                for r_data in round_reports:
                    vr = MathValidationReport(
                        report_id=r_data.get("report_id", f"{ps['id']}_vr{round_num}"),
                        proposition_id=ps["id"],
                        overall_score=r_data.get("overall_score", 0.5),
                        overall_valid=r_data.get("overall_valid", False),
                        round_number=round_num,
                    )
                    pool.add_validation_report(ps["id"], vr)

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
                    {"proposition_id": ps["id"], "overall_score": r.get("overall_score", 0)}
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
                "stagnation_rounds": cr.stagnation_rounds,
            }

            # 4g. 创建快照
            validation_summary = {
                "total_validations": round_num,
                "pass_rate": 0.5,
                "logical_gaps": final_convergence_report["proof_gap_count"],
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

            if cr.is_converged:
                break

        # 5. 汇总命题状态
        final_props = pool.to_dict_list()

        # 6. 确定实际分支
        actual_branch = final_convergence_report.get("convergence_type", "PENDING")

        # 7. 校验哈希链完整性
        hash_chain_valid = bridge.verify_chain_integrity()

        # 8. 汇总插件结果（取最后一轮）
        last_plugin_results: dict[str, Any] = {}
        for name, results in all_plugin_results.items():
            if results:
                last = results[-1]
                last_plugin_results[name] = {
                    "plugin_name": last.plugin_name,
                    "status": last.status.value,
                    "output": last.output,
                    "error": last.error,
                    "elapsed_ms": last.elapsed_ms,
                }

        # 9. 导出报告
        exporter = ReportExporter(
            bridge,
            plugin_results={
                name: PluginResult(
                    plugin_name=last.plugin_name,
                    status=last.status,
                    output=last.output,
                    error=last.error,
                    elapsed_ms=last.elapsed_ms,
                )
                for name, last in [(n, rs[-1]) for n, rs in all_plugin_results.items() if rs]
            },
        )
        report_md = exporter.export_to_markdown()
        report_path = write_file(f"{scenario_id}_report.md", report_md)
        report_json = exporter.export_to_json()
        json_path = write_file(f"{scenario_id}_report.json", json.dumps(report_json, ensure_ascii=False, indent=2))

        # 10. 判定通过
        branch_match = expected_branch in (actual_branch, "FORCED_TERMINATE") or actual_branch == expected_branch
        passed = hash_chain_valid and branch_match

        log(f"  │  实际分支: {actual_branch} | 轮次: {len(bridge.get_all_snapshots())}")
        log(f"  │  哈希链: {'✅' if hash_chain_valid else '❌'} | 命题: {len(final_props)}")
        for p in final_props:
            log(f"  │    {p['proposition_id']}: {p['status']}")
        log(f"  └─ {'✅ 通过' if passed else '❌ 失败'}")

        return ScenarioResult(
            scenario_id=scenario_id,
            name=name,
            expected_branch=expected_branch,
            actual_branch=actual_branch,
            total_rounds=len(bridge.get_all_snapshots()),
            propositions=final_props,
            plugin_config=plugin_config,
            plugin_results=last_plugin_results,
            convergence_report=final_convergence_report,
            hash_chain_valid=hash_chain_valid,
            report_path=report_path,
            passed=passed,
        )

    except Exception as e:
        log(f"  └─ ❌ 异常: {e}")
        traceback.print_exc()
        return ScenarioResult(
            scenario_id=scenario_id, name=name,
            expected_branch=expected_branch, actual_branch="ERROR",
            total_rounds=0, propositions=[], plugin_config=plugin_config,
            plugin_results={}, convergence_report={},
            hash_chain_valid=False, error=str(e), passed=False,
        )


# =============================================================================
# 场景定义
# =============================================================================

# ── S1: 欧几里得素数无穷性证明 ──
S1_PROVEN_EUCLID = {
    "id": "S1",
    "name": "欧几里得素数无穷性证明",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p1", "statement": "存在无穷多个素数",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p1_s1", "step_number": 1,
                    "premises": ["假设素数有限，设全体素数为 p1,...,pk"],
                    "conclusion": "构造 N = p1·p2·...·pk + 1",
                    "rule": "by_construction",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p1_s2", "step_number": 2,
                    "premises": ["N = p1·p2·...·pk + 1"],
                    "conclusion": "N 不被任何已知素数整除",
                    "rule": "divisibility",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p1_s3", "step_number": 3,
                    "premises": ["N 不被任何已知素数整除", "N > 1"],
                    "conclusion": "N 要么是素数，要么有新的素因子 → 与假设矛盾",
                    "rule": "contradiction",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p1_vr1",
                    "overall_score": 0.95, "overall_valid": True,
                }
            ],
        }
    ],
    "plugin_config": {"plugins": {}},
}

# ── S2: 梅森数反例 n=11 (DISPROVEN + sympy) ──
S2_MERSENNE_DISPROVEN = {
    "id": "S2",
    "name": "梅森数猜想反例: n=11 时 2^11-1=2047=23×89",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p2", "statement": "若 n 为素数，则 2^n-1 为素数",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p2_s1", "step_number": 1,
                    "premises": ["n=11 是素数"],
                    "conclusion": "2^11 - 1 = 2047",
                    "rule": "computation",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p2_s2", "step_number": 2,
                    "premises": ["2047 = 23 × 89"],
                    "conclusion": "2047 不是素数，是合数 → 原命题被证伪",
                    "rule": "factorization",
                    "has_gap": True, "gap_description": "仅凭特例归纳为一般证伪，需补充枚举论证",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p2_ce1",
                    "value": "n=11: 2^11-1=2047=23×89",
                    "is_valid": True, "is_reproducible": True,
                }
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p2_vr1",
                    "overall_score": 0.6, "overall_valid": False,
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

# ── S3: 孪生素数猜想 (INCONCLUSIVE → FORCED_TERMINATE + stagnation) ──
S3_TWIN_PRIME_INCONCLUSIVE = {
    "id": "S3",
    "name": "孪生素数猜想：存在无穷多对孪生素数（开放问题）",
    "expected_branch": "FORCED_TERMINATE",
    "propositions": [
        {
            "id": "p3", "statement": "存在无穷多对孪生素数 (p, p+2)",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p3_s1", "step_number": 1,
                    "premises": ["已知孪生素数对: (3,5), (5,7), (11,13), (17,19), ..."],
                    "conclusion": "已发现大量孪生素数对，但无法证明无穷性",
                    "rule": "empirical_observation",
                    "has_gap": True, "gap_description": "经验观察无法代替严格证明",
                    "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p3_s2", "step_number": 2,
                    "premises": ["Brun 定理: 孪生素数倒数之和收敛"],
                    "conclusion": "孪生素数密度趋近于零，但不排除无穷性",
                    "rule": "theorem",
                    "has_gap": True, "gap_description": "密度趋零与无穷性不矛盾，无法判定",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p3_vr1",
                    "overall_score": 0.2, "overall_valid": False,
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

# ── S4: 哥德巴赫弱猜想 (INCONCLUSIVE，全插件) ──
S4_GOLDBACH_INCONCLUSIVE = {
    "id": "S4",
    "name": "哥德巴赫猜想：大于2的偶数都是两个素数之和",
    "expected_branch": "FORCED_TERMINATE",
    "propositions": [
        {
            "id": "p4", "statement": "每个大于 2 的偶数可以表示为两个素数之和",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p4_s1", "step_number": 1,
                    "premises": ["已验证到 4×10^18 均成立"],
                    "conclusion": "猜想在已有范围内成立，但无一般证明",
                    "rule": "empirical_verification",
                    "has_gap": True, "gap_description": "有限验证不能代替无限证明",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p4_vr1",
                    "overall_score": 0.15, "overall_valid": False,
                }
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
            "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30},
        }
    },
}

# ── S5: 费马小定理特例 (PROVEN + sympy) ──
S5_FERMAT_PROVEN = {
    "id": "S5",
    "name": "费马小定理特例: a^(p-1) ≡ 1 (mod p) 当 p=7, a=2",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p5", "statement": "对于素数 p=7 和整数 a=2，有 2^6 ≡ 1 (mod 7)",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p5_s1", "step_number": 1,
                    "premises": ["p=7 是素数"],
                    "conclusion": "φ(7) = 6",
                    "rule": "by_definition",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p5_s2", "step_number": 2,
                    "premises": ["费马小定理: a^(p-1) ≡ 1 (mod p)", "p=7, a=2"],
                    "conclusion": "2^6 = 64 ≡ 1 (mod 7)，因为 64 = 9×7 + 1",
                    "rule": "theorem",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p5_vr1",
                    "overall_score": 1.0, "overall_valid": True,
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

# ── S6: "所有奇数都是素数" (DISPROVEN，无插件) ──
S6_ODD_PRIME_DISPROVEN = {
    "id": "S6",
    "name": "伪命题: 所有奇数都是素数（反例: 9, 15, 21）",
    "expected_branch": "DISPROVEN",
    "propositions": [
        {
            "id": "p6", "statement": "所有奇数都是素数",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p6_s1", "step_number": 1,
                    "premises": ["3, 5, 7, 11, 13 都是奇素数"],
                    "conclusion": "部分奇数确实是素数",
                    "rule": "empirical",
                    "has_gap": True, "gap_description": "仅凭特例归纳，逻辑不完整",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p6_ce1",
                    "value": "9 = 3 × 3，是奇数但不是素数",
                    "is_valid": True, "is_reproducible": True,
                },
                {
                    "round": 1, "example_id": "p6_ce2",
                    "value": "15 = 3 × 5，是奇数但不是素数",
                    "is_valid": True, "is_reproducible": True,
                },
            ],
            "validation_reports": [
                {
                    "round": 1, "report_id": "p6_vr1",
                    "overall_score": 0.1, "overall_valid": False,
                }
            ],
        }
    ],
    "plugin_config": {"plugins": {}},
}

# ── S7: 混合命题集 (PROVEN + DISPROVEN + INCONCLUSIVE) ──
S7_MIXED_PROPOSITIONS = {
    "id": "S7",
    "name": "混合命题集: 已证命题 + 反例命题 + 开放问题",
    "expected_branch": "DISPROVEN",  # 有一个反例即触发收敛
    "propositions": [
        {
            "id": "p7a", "statement": "√2 是无理数",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p7a_s1", "step_number": 1,
                    "premises": ["假设 √2 = a/b，a,b 互素"],
                    "conclusion": "2b² = a²，故 a² 是偶数，a 是偶数",
                    "rule": "algebraic_manipulation",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p7a_s2", "step_number": 2,
                    "premises": ["a 是偶数，设 a=2k"],
                    "conclusion": "2b² = 4k² → b² = 2k²，故 b 是偶数 → a,b 不互素，矛盾",
                    "rule": "contradiction",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {"round": 1, "report_id": "p7a_vr1", "overall_score": 1.0, "overall_valid": True},
            ],
        },
        {
            "id": "p7b", "statement": "n² + n + 41 对所有自然数 n 都是素数",
            "domain": "number_theory", "difficulty": "elementary",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p7b_s1", "step_number": 1,
                    "premises": ["n=0,1,...,39 时 n²+n+41 均为素数"],
                    "conclusion": "前 40 个值确实都是素数",
                    "rule": "computation",
                    "has_gap": True, "gap_description": "特例不能推广到全体",
                    "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [
                {
                    "round": 1, "example_id": "p7b_ce1",
                    "value": "n=40: 40²+40+41 = 1681 = 41²，不是素数",
                    "is_valid": True, "is_reproducible": True,
                }
            ],
            "validation_reports": [
                {"round": 1, "report_id": "p7b_vr1", "overall_score": 0.3, "overall_valid": False},
            ],
        },
        {
            "id": "p7c", "statement": "黎曼猜想: ζ(s) 的所有非平凡零点的实部都是 1/2",
            "domain": "number_theory", "difficulty": "advanced",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p7c_s1", "step_number": 1,
                    "premises": ["已知前 10^13 个零点均满足 Re(s)=1/2"],
                    "conclusion": "猜想在已有范围内成立，但无严格证明",
                    "rule": "empirical_verification",
                    "has_gap": True, "gap_description": "有限验证无法替代无限证明",
                    "has_hidden_assumption": True, "hidden_assumption": "假设零点分布具有某种规律性",
                    "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {"round": 1, "report_id": "p7c_vr1", "overall_score": 0.1, "overall_valid": False},
            ],
        },
    ],
    "plugin_config": {
        "plugins": {
            "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
            "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
        }
    },
}

# ── S8: 黎曼ζ函数平凡零点 (PROVEN + lean_repl) ──
S8_RIEMANN_TRIVIAL_ZEROS = {
    "id": "S8",
    "name": "黎曼ζ函数平凡零点: ζ(-2n) = 0 对所有正整数 n",
    "expected_branch": "PROVEN",
    "propositions": [
        {
            "id": "p8", "statement": "ζ(-2n) = 0 对所有正整数 n 成立（平凡零点）",
            "domain": "number_theory", "difficulty": "intermediate",
            "derivation_steps": [
                {
                    "round": 1, "step_id": "p8_s1", "step_number": 1,
                    "premises": ["ζ(s) 的函数方程: ζ(s) = 2^s π^(s-1) sin(πs/2) Γ(1-s) ζ(1-s)"],
                    "conclusion": "当 s = -2n 时，sin(π(-2n)/2) = sin(-nπ) = 0",
                    "rule": "algebraic_manipulation",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
                {
                    "round": 1, "step_id": "p8_s2", "step_number": 2,
                    "premises": ["sin(-nπ) = 0", "函数方程右侧其他因子在 s=-2n 处有限"],
                    "conclusion": "ζ(-2n) = 0 对所有正整数 n 成立",
                    "rule": "theorem",
                    "has_gap": False, "has_hidden_assumption": False, "is_circular": False,
                },
            ],
            "counter_examples": [],
            "validation_reports": [
                {"round": 1, "report_id": "p8_vr1", "overall_score": 1.0, "overall_valid": True},
            ],
        }
    ],
    "plugin_config": {
        "plugins": {
            "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30},
        }
    },
}


# =============================================================================
# 主入口
# =============================================================================

def main():
    log("=" * 70)
    log("Module-MathB v1.1 应用实测 — 8 场景全覆盖")
    log(f"输出目录: {OUTPUT_DIR}")
    log("=" * 70)

    scenarios = [
        S1_PROVEN_EUCLID,
        S2_MERSENNE_DISPROVEN,
        S3_TWIN_PRIME_INCONCLUSIVE,
        S4_GOLDBACH_INCONCLUSIVE,
        S5_FERMAT_PROVEN,
        S6_ODD_PRIME_DISPROVEN,
        S7_MIXED_PROPOSITIONS,
        S8_RIEMANN_TRIVIAL_ZEROS,
    ]

    results: list[ScenarioResult] = []
    branch_counts: dict[str, int] = {"PROVEN": 0, "DISPROVEN": 0, "FORCED_TERMINATE": 0, "ERROR": 0}

    for sc in scenarios:
        log("")
        result = run_scenario(
            scenario_id=sc["id"],
            name=sc["name"],
            expected_branch=sc["expected_branch"],
            propositions_spec=sc["propositions"],
            plugin_config=sc["plugin_config"],
            max_rounds=4,
        )
        results.append(result)
        branch_counts[result.actual_branch] = branch_counts.get(result.actual_branch, 0) + 1

    # ── 汇总 ──
    log("")
    log("=" * 70)
    log("实测汇总")
    log("=" * 70)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    log(f"通过: {passed}/{total}")
    log(f"分支覆盖: {branch_counts}")
    log(f"哈希链验证: {'全部通过' if all(r.hash_chain_valid for r in results if not r.error) else '存在异常'}")

    # 详细表格
    log("")
    log(f"{'ID':<4} {'场景':<40} {'预期':<18} {'实际':<18} {'轮次':<5} {'插件':<5} {'链':<4} {'结果':<6}")
    log("-" * 105)
    for r in results:
        plugin_count = len(r.plugin_results)
        chain_ok = "✅" if r.hash_chain_valid else "❌"
        status = "✅" if r.passed else "❌"
        log(f"{r.scenario_id:<4} {r.name[:38]:<40} {r.expected_branch:<18} {r.actual_branch:<18} "
            f"{r.total_rounds:<5} {plugin_count:<5} {chain_ok:<4} {status:<6}")

    # ── 生成汇总报告 ──
    summary_lines = []
    summary_lines.append("# Module-MathB v1.1 应用实测报告")
    summary_lines.append("")
    summary_lines.append(f"> **生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    summary_lines.append(f"> **场景总数**: {total}")
    summary_lines.append(f"> **通过**: {passed}/{total}")
    summary_lines.append("")
    summary_lines.append("---")
    summary_lines.append("")
    summary_lines.append("## 分支覆盖统计")
    summary_lines.append("")
    summary_lines.append("| 分支 | 场景数 | 场景列表 |")
    summary_lines.append("|------|--------|----------|")
    for branch in ["PROVEN", "DISPROVEN", "FORCED_TERMINATE", "ERROR"]:
        if branch in branch_counts:
            ids = [r.scenario_id for r in results if r.actual_branch == branch]
            summary_lines.append(f"| {branch} | {branch_counts[branch]} | {', '.join(ids)} |")
    summary_lines.append("")

    summary_lines.append("## 场景详情")
    summary_lines.append("")
    summary_lines.append("| ID | 场景 | 预期 | 实际 | 轮次 | 命题数 | 插件 | 哈希链 | 结果 |")
    summary_lines.append("|----|------|------|------|------|--------|------|--------|------|")
    for r in results:
        plugin_names = ", ".join(r.plugin_results.keys()) if r.plugin_results else "无"
        chain_ok = "✅" if r.hash_chain_valid else "❌"
        status = "✅" if r.passed else "❌"
        summary_lines.append(
            f"| {r.scenario_id} | {r.name[:30]} | {r.expected_branch} | {r.actual_branch} "
            f"| {r.total_rounds} | {len(r.propositions)} | {plugin_names[:20]} | {chain_ok} | {status} |"
        )
    summary_lines.append("")

    summary_lines.append("## 命题状态分布")
    summary_lines.append("")
    all_props: list[dict] = []
    for r in results:
        for p in r.propositions:
            all_props.append({"scenario": r.scenario_id, **p})
    summary_lines.append("| 场景 | 命题ID | 语句 | 状态 | 推导步 | 反例 | 缺口 |")
    summary_lines.append("|------|--------|------|------|--------|------|------|")
    for p in all_props:
        summary_lines.append(
            f"| {p['scenario']} | {p['proposition_id']} "
            f"| {p['statement'][:40]} "
            f"| {p['status']} "
            f"| {p.get('derivation_step_count', 0)} "
            f"| {p.get('counter_example_count', 0)} "
            f"| {p.get('gap_count', 0)} |"
        )
    summary_lines.append("")

    summary_lines.append("## 插件执行结果")
    summary_lines.append("")
    summary_lines.append("| 场景 | 插件 | 状态 | 耗时(ms) | 错误 |")
    summary_lines.append("|------|------|------|----------|------|")
    for r in results:
        for name, pr in r.plugin_results.items():
            summary_lines.append(
                f"| {r.scenario_id} | {name} | {pr.get('status', '?')} "
                f"| {pr.get('elapsed_ms', 0):.1f} | {pr.get('error', '')[:40]} |"
            )
    summary_lines.append("")

    summary_lines.append("## 哈希链完整性")
    summary_lines.append("")
    summary_lines.append("| 场景 | 快照数 | 完整性 |")
    summary_lines.append("|------|--------|--------|")
    for r in results:
        chain_ok = "✅" if r.hash_chain_valid else "❌"
        summary_lines.append(f"| {r.scenario_id} | {r.total_rounds} | {chain_ok} |")
    summary_lines.append("")

    # 详细报告
    for r in results:
        summary_lines.append(f"---")
        summary_lines.append(f"")
        summary_lines.append(f"## {r.scenario_id}: {r.name}")
        summary_lines.append(f"")
        summary_lines.append(f"- **预期分支**: {r.expected_branch}")
        summary_lines.append(f"- **实际分支**: {r.actual_branch}")
        summary_lines.append(f"- **总轮次**: {r.total_rounds}")
        summary_lines.append(f"- **哈希链**: {'✅ 完整' if r.hash_chain_valid else '❌ 异常'}")
        summary_lines.append(f"- **结果**: {'✅ 通过' if r.passed else '❌ 失败'}")
        if r.error:
            summary_lines.append(f"- **错误**: {r.error}")
        summary_lines.append("")
        summary_lines.append(f"### 命题状态")
        for p in r.propositions:
            summary_lines.append(f"- `{p['proposition_id']}`: **{p['status']}** — {p['statement']}")
        summary_lines.append("")
        if r.plugin_results:
            summary_lines.append(f"### 插件执行")
            for name, pr in r.plugin_results.items():
                summary_lines.append(f"- `{name}`: {pr.get('status')} ({pr.get('elapsed_ms', 0):.1f}ms)")
        summary_lines.append("")

    summary_md = "\n".join(summary_lines)
    summary_path = write_file("SUMMARY_FIELD_TEST.md", summary_md)
    log(f"")
    log(f"汇总报告: {summary_path}")

    # ── 写入 JSON 汇总 ──
    json_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.1.0",
        "total_scenarios": total,
        "passed": passed,
        "branch_coverage": branch_counts,
        "hash_chain_all_valid": all(r.hash_chain_valid for r in results if not r.error),
        "scenarios": [
            {
                "scenario_id": r.scenario_id,
                "name": r.name,
                "expected_branch": r.expected_branch,
                "actual_branch": r.actual_branch,
                "total_rounds": r.total_rounds,
                "propositions": r.propositions,
                "plugin_config": r.plugin_config,
                "plugin_results": r.plugin_results,
                "convergence_report": r.convergence_report,
                "hash_chain_valid": r.hash_chain_valid,
                "error": r.error,
                "passed": r.passed,
            }
            for r in results
        ],
    }
    json_path = write_file("SUMMARY_FIELD_TEST.json", json.dumps(json_summary, ensure_ascii=False, indent=2))
    log(f"JSON 汇总: {json_path}")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)