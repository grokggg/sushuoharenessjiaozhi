"""
module_math_b.tests_mathb.run_e2e_v1_1 — v1.1 端到端验证

两轮验证：
  ① 梅森数猜想 demo 开启 sympy 插件
  ② 开放类子命题触发 INCONCLUSIVE 停滞分支

输出：完整执行日志、插件配置、报告、测试结果
"""

import os
import sys
import json
import time
import traceback
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from module_math_b.math_router import MathRouter, MathWorkflowResult
from module_math_b.report_exporter import ReportExporter, ReportConfig
from module_math_b.plugins.plugin_registry import PluginRegistry, PluginConfig, PluginResult, PluginStatus
from module_math_b.plugins.sympy_bridge import SympyBridge
from module_math_b.plugins.stagnation_analyzer import StagnationAnalyzer


# =============================================================================
# 输出目录
# =============================================================================

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "e2e_output_v1_1",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg: str) -> None:
    """带时间戳的日志"""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def write_file(filename: str, content: str) -> str:
    """写入文件并返回路径"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# =============================================================================
# E2E ①: 梅森数猜想 demo 开启 sympy 插件
# =============================================================================

def run_e2e_mersenne_with_sympy() -> dict:
    """
    梅森数猜想验证：若 n 为素数，则 2^n-1 为素数。

    预期结果：
      - 子命题A（正向）: 若 2^n-1 为素数 ⇒ n 是素数 → PROVEN
      - 子命题B（反向）: 若 n 为素数 ⇒ 2^n-1 是素数 → DISPROVEN (反例 n=11)
      - sympy 插件验证 2047 = 23 × 89
    """
    log("=" * 70)
    log("E2E ①: 梅森数猜想验证 — 开启 sympy 插件")
    log("=" * 70)

    task = {
        "query": (
            "验证梅森素数猜想：若 n 为素数，则 2^n-1 为素数。"
            "请拆分为两个子命题："
            "子命题A：若 2^n-1 为素数 ⇒ n 是素数（正向）"
            "子命题B：若 n 为素数 ⇒ 2^n-1 是素数（反向）"
            "请使用 sympy 插件验证计算结果，搜索反例。"
        ),
        "task_id": "e2e_mersenne_sympy",
        "task_type": "number_theory",
        "mathb_config": {
            "plugins": {
                "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
                "stagnation_analyzer": {"enabled": False},
                "lean_repl_bridge": {"enabled": False},
            }
        },
    }

    log(f"任务配置: {json.dumps(task['mathb_config'], ensure_ascii=False)}")

    round_info: list[dict] = []

    def on_round(r, info):
        round_info.append(info)
        log(f"  第 {r} 轮: propositions={info.get('proposition_count', 0)}, "
            f"proven={info.get('proven', 0)}, disproven={info.get('disproven', 0)}, "
            f"converged={info.get('converged', False)}, type={info.get('convergence_type', '')}")

    router = MathRouter()
    result = router.execute_math_workflow(task, on_round_complete=on_round)

    log(f"最终状态: {result.final_status}")
    log(f"总轮次: {result.total_rounds}")
    log(f"命题数: {len(result.propositions)}")

    for prop in result.propositions:
        log(f"  命题 {prop['proposition_id']}: status={prop['status']}, "
            f"steps={prop.get('derivation_step_count', 0)}, "
            f"gaps={prop.get('gap_count', 0)}")

    # 插件结果
    plugin_results = result.plugin_results
    log(f"插件结果数: {len(plugin_results)}")
    for name, pr in plugin_results.items():
        log(f"  {name}: status={pr.get('status')}, error={pr.get('error', '')[:80]}")

    # 生成报告
    report_lines = []
    report_lines.append("# E2E 验证 ①: 梅森数猜想 + SymPy 插件")
    report_lines.append("")
    report_lines.append(f"## 任务配置")
    report_lines.append("```json")
    report_lines.append(json.dumps(task["mathb_config"], ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append(f"## 执行结果")
    report_lines.append(f"- **最终状态**: `{result.final_status}`")
    report_lines.append(f"- **总轮次**: {result.total_rounds}")
    report_lines.append(f"- **错误信息**: {result.error or '无'}")
    report_lines.append("")
    report_lines.append(f"## 命题状态")
    report_lines.append("| 命题ID | 陈述 | 状态 | 推导步数 | 缺口数 |")
    report_lines.append("|--------|------|------|----------|--------|")
    for prop in result.propositions:
        report_lines.append(
            f"| `{prop['proposition_id']}` "
            f"| {prop.get('statement', '')[:60]} "
            f"| `{prop['status']}` "
            f"| {prop.get('derivation_step_count', 0)} "
            f"| {prop.get('gap_count', 0)} |"
        )
    report_lines.append("")
    report_lines.append(f"## 插件执行结果")
    report_lines.append("| 插件 | 状态 | 耗时(ms) | 错误 |")
    report_lines.append("|------|------|----------|------|")
    for name, pr in plugin_results.items():
        report_lines.append(
            f"| `{name}` | {pr.get('status')} | {pr.get('elapsed_ms', 0):.1f} | "
            f"{pr.get('error', '')[:60]} |"
        )
    report_lines.append("")
    report_lines.append(f"## 收敛判定")
    report_lines.append(f"```json")
    report_lines.append(json.dumps(result.convergence_report, ensure_ascii=False, indent=2))
    report_lines.append("```")

    report_md = "\n".join(report_lines)
    report_path = write_file("e2e_01_mersenne_sympy_report.md", report_md)
    log(f"报告已生成: {report_path}")

    # 额外: 直接使用 sympy 验证 2047
    sympy_check = _verify_mersenne_with_sympy()
    log(f"SymPy 直接验证: {json.dumps(sympy_check, ensure_ascii=False)}")

    return {
        "scenario": "mersenne_sympy",
        "final_status": result.final_status,
        "total_rounds": result.total_rounds,
        "propositions": result.propositions,
        "plugin_results": plugin_results,
        "sympy_direct_check": sympy_check,
        "report_path": report_path,
    }


def _verify_mersenne_with_sympy() -> dict:
    """直接使用 SymPy 验证梅森数反例"""
    bridge = SympyBridge()
    if not bridge.is_available:
        return {"error": "SymPy 不可用"}

    checks = []
    # 验证 n=11 时 2^11-1=2047 不是素数
    result = bridge.execute({"operation": "isprime_verbose", "n": 2047})
    checks.append({
        "n": 11,
        "value": 2047,
        "is_prime": result.output.get("is_prime") if result.status == PluginStatus.ENABLED else None,
        "factors": result.output.get("factors") if result.status == PluginStatus.ENABLED else None,
        "steps": result.output.get("steps") if result.status == PluginStatus.ENABLED else [],
    })

    # 验证 n=2,3,5,7 时 2^n-1 是素数
    for n in [2, 3, 5, 7]:
        val = 2**n - 1
        result = bridge.execute({"operation": "is_prime", "n": val})
        checks.append({
            "n": n,
            "value": val,
            "is_prime": result.output.get("is_prime") if result.status == PluginStatus.ENABLED else None,
        })

    return {"checks": checks}


# =============================================================================
# E2E ②: 开放类子命题触发 INCONCLUSIVE 停滞
# =============================================================================

def run_e2e_inconclusive_stagnation() -> dict:
    """
    开放类子命题：孪生素数猜想（存在无穷多对孪生素数）

    这是一个开放问题，没有已知证明或反例。
    预期：连续多轮 INCONCLUSIVE，触发 FORCED_TERMINATE。
    开启 stagnation_analyzer 插件分析停滞根因。
    """
    log("=" * 70)
    log("E2E ②: 开放类子命题 — 触发 INCONCLUSIVE 停滞")
    log("=" * 70)

    task = {
        "query": (
            "证明或证伪孪生素数猜想：存在无穷多对孪生素数（即差为 2 的素数对）。"
            "请给出严格证明或构造反例。"
            "这是著名的开放问题，尚无已知证明或反例。"
        ),
        "task_id": "e2e_inconclusive_twin",
        "task_type": "number_theory",
        "mathb_config": {
            "plugins": {
                "sympy_bridge": {"enabled": False},
                "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
                "lean_repl_bridge": {"enabled": False},
            }
        },
    }

    log(f"任务配置: {json.dumps(task['mathb_config'], ensure_ascii=False)}")

    round_info: list[dict] = []

    def on_round(r, info):
        round_info.append(info)
        log(f"  第 {r} 轮: propositions={info.get('proposition_count', 0)}, "
            f"proven={info.get('proven', 0)}, disproven={info.get('disproven', 0)}, "
            f"converged={info.get('converged', False)}, type={info.get('convergence_type', '')}")

    router = MathRouter()
    result = router.execute_math_workflow(task, on_round_complete=on_round)

    log(f"最终状态: {result.final_status}")
    log(f"总轮次: {result.total_rounds}")
    log(f"命题数: {len(result.propositions)}")

    for prop in result.propositions:
        log(f"  命题 {prop['proposition_id']}: status={prop['status']}, "
            f"steps={prop.get('derivation_step_count', 0)}, "
            f"gaps={prop.get('gap_count', 0)}")

    # 插件结果
    plugin_results = result.plugin_results
    log(f"插件结果数: {len(plugin_results)}")
    for name, pr in plugin_results.items():
        log(f"  {name}: status={pr.get('status')}, error={pr.get('error', '')[:80]}")

    # 生成报告
    report_lines = []
    report_lines.append("# E2E 验证 ②: 开放类子命题 — INCONCLUSIVE 停滞")
    report_lines.append("")
    report_lines.append(f"## 任务配置")
    report_lines.append("```json")
    report_lines.append(json.dumps(task["mathb_config"], ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append(f"## 执行结果")
    report_lines.append(f"- **最终状态**: `{result.final_status}`")
    report_lines.append(f"- **总轮次**: {result.total_rounds}")
    report_lines.append(f"- **错误信息**: {result.error or '无'}")
    report_lines.append("")
    report_lines.append(f"## 命题状态")
    report_lines.append("| 命题ID | 陈述 | 状态 | 推导步数 | 缺口数 |")
    report_lines.append("|--------|------|------|----------|--------|")
    for prop in result.propositions:
        report_lines.append(
            f"| `{prop['proposition_id']}` "
            f"| {prop.get('statement', '')[:60]} "
            f"| `{prop['status']}` "
            f"| {prop.get('derivation_step_count', 0)} "
            f"| {prop.get('gap_count', 0)} |"
        )
    report_lines.append("")
    report_lines.append(f"## 停滞分析结果")
    report_lines.append("| 插件 | 状态 | 耗时(ms) | 错误 |")
    report_lines.append("|------|------|----------|------|")
    for name, pr in plugin_results.items():
        report_lines.append(
            f"| `{name}` | {pr.get('status')} | {pr.get('elapsed_ms', 0):.1f} | "
            f"{pr.get('error', '')[:60]} |"
        )
    report_lines.append("")
    report_lines.append(f"## 收敛判定")
    report_lines.append(f"```json")
    report_lines.append(json.dumps(result.convergence_report, ensure_ascii=False, indent=2))
    report_lines.append("```")
    report_lines.append("")
    report_lines.append(f"## 每轮详情")
    for ri in round_info:
        report_lines.append(f"- 轮次 {ri.get('round', '?')}: "
                           f"converged={ri.get('converged', False)}, "
                           f"type={ri.get('convergence_type', '')}")

    report_md = "\n".join(report_lines)
    report_path = write_file("e2e_02_inconclusive_stagnation_report.md", report_md)
    log(f"报告已生成: {report_path}")

    return {
        "scenario": "inconclusive_stagnation",
        "final_status": result.final_status,
        "total_rounds": result.total_rounds,
        "propositions": result.propositions,
        "plugin_results": plugin_results,
        "round_info": round_info,
        "report_path": report_path,
    }


# =============================================================================
# 插件配置样例 JSON
# =============================================================================

def generate_plugin_config_samples() -> str:
    """生成插件配置样例 JSON"""
    samples = {
        "description": "Module-MathB v1.1 插件配置样例",
        "version": "1.1.0",
        "samples": [
            {
                "name": "sympy 插件启用 — 梅森数验证",
                "mathb_config": {
                    "plugins": {
                        "sympy_bridge": {"enabled": True, "timeout_seconds": 10, "memory_limit_mb": 128},
                        "lean_repl_bridge": {"enabled": False},
                        "stagnation_analyzer": {"enabled": False},
                    }
                },
                "usage": "用于素数判定、因式分解等符号计算验证",
            },
            {
                "name": "停滞分析插件启用 — 开放问题探索",
                "mathb_config": {
                    "plugins": {
                        "sympy_bridge": {"enabled": False},
                        "lean_repl_bridge": {"enabled": False},
                        "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10, "memory_limit_mb": 64},
                    }
                },
                "usage": "用于分析数学迭代停滞的根因，生成诊断建议",
            },
            {
                "name": "全插件启用 — 完整形式化验证",
                "mathb_config": {
                    "plugins": {
                        "sympy_bridge": {"enabled": True, "timeout_seconds": 10, "memory_limit_mb": 128},
                        "lean_repl_bridge": {"enabled": True, "timeout_seconds": 30, "memory_limit_mb": 256},
                        "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10, "memory_limit_mb": 64},
                    }
                },
                "usage": "完整验证流水线：符号计算 + 形式化验证 + 停滞分析",
                "note": "lean_repl_bridge 需要本地安装 Lean 4，否则优雅降级",
            },
            {
                "name": "默认配置（插件全关）",
                "mathb_config": {
                    "plugins": {}
                },
                "usage": "所有插件默认关闭，仅使用 v1.0 核心功能",
            },
            {
                "name": "自定义超时限制",
                "mathb_config": {
                    "plugins": {
                        "sympy_bridge": {
                            "enabled": True,
                            "timeout_seconds": 5,
                            "memory_limit_mb": 64,
                            "extra_args": {"precision": "high"}
                        },
                    }
                },
                "usage": "通过 extra_args 传递插件特定参数",
            },
        ],
        "plugin_descriptions": {
            "sympy_bridge": "SymPy 符号计算桥接 — 素数判定、因式分解、模运算",
            "lean_repl_bridge": "Lean 4 REPL 形式化验证桥接 — 需要本地安装 Lean 4",
            "stagnation_analyzer": "停滞根因分析 — 缺口模式识别、推导停滞检测、诊断建议",
        },
        "integration_example": {
            "task_json": {
                "query": "验证命题：若 n 为素数，则 2^n-1 为素数",
                "task_id": "example_task_001",
                "task_type": "number_theory",
                "mathb_config": {
                    "plugins": {
                        "sympy_bridge": {"enabled": True},
                        "stagnation_analyzer": {"enabled": True},
                    }
                },
            },
            "expected_behavior": (
                "1. math_router 识别 MATH_TASK → 初始化数学集群\n"
                "2. 加载插件配置 → sympy_bridge 和 stagnation_analyzer 启用\n"
                "3. 每轮迭代执行已启用插件\n"
                "4. 收敛后导出报告，包含插件执行结果\n"
                "5. 会话结束，插件和模块完全销毁"
            ),
        },
    }

    content = json.dumps(samples, ensure_ascii=False, indent=2)
    path = write_file("plugin_config_samples.json", content)
    return path


# =============================================================================
# 主入口
# =============================================================================

def main():
    log("Module-MathB v1.1 端到端验证")
    log(f"输出目录: {OUTPUT_DIR}")
    log("")

    # 生成插件配置样例
    config_path = generate_plugin_config_samples()
    log(f"插件配置样例: {config_path}")
    log("")

    results = {}

    # E2E ①
    try:
        results["e2e_01"] = run_e2e_mersenne_with_sympy()
        log("E2E ① 完成")
    except Exception as e:
        log(f"E2E ① 失败: {e}")
        traceback.print_exc()
        results["e2e_01"] = {"error": str(e)}

    log("")

    # E2E ②
    try:
        results["e2e_02"] = run_e2e_inconclusive_stagnation()
        log("E2E ② 完成")
    except Exception as e:
        log(f"E2E ② 失败: {e}")
        traceback.print_exc()
        results["e2e_02"] = {"error": str(e)}

    log("")

    # 汇总
    log("=" * 70)
    log("E2E 验证汇总")
    log("=" * 70)

    e1 = results.get("e2e_01", {})
    e2 = results.get("e2e_02", {})

    log(f"E2E ① 梅森数+SymPy: 最终状态={e1.get('final_status', 'ERROR')}, "
        f"轮次={e1.get('total_rounds', 0)}, "
        f"插件结果数={len(e1.get('plugin_results', {}))}")
    log(f"E2E ② INCONCLUSIVE停滞: 最终状态={e2.get('final_status', 'ERROR')}, "
        f"轮次={e2.get('total_rounds', 0)}, "
        f"插件结果数={len(e2.get('plugin_results', {}))}")

    # 写入汇总
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.1.0",
        "e2e_01": {
            "scenario": "梅森数猜想 + SymPy 插件",
            "final_status": e1.get("final_status", "ERROR"),
            "total_rounds": e1.get("total_rounds", 0),
            "plugin_results_count": len(e1.get("plugin_results", {})),
        },
        "e2e_02": {
            "scenario": "开放类子命题 INCONCLUSIVE 停滞",
            "final_status": e2.get("final_status", "ERROR"),
            "total_rounds": e2.get("total_rounds", 0),
            "plugin_results_count": len(e2.get("plugin_results", {})),
        },
    }
    summary_path = write_file("e2e_summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    log(f"汇总已保存: {summary_path}")

    return results


if __name__ == "__main__":
    main()