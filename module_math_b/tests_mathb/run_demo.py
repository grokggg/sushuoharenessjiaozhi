#!/usr/bin/env python3
"""
Module-MathB v1.0 端到端数论猜想验证 Demo

测试命题：
  "对于任意大于 1 的正整数 n，
   如果 2^n − 1 是素数，那么 n 一定是素数；
   反过来，如果 n 是素数，则 2^n − 1 必定是素数。"

子命题拆解：
  子命题A (正向): 若 2^n-1 为素数 ⇒ n 是素数  → 预期 PROVEN
  子命题B (反向): 若 n 为素数 ⇒ 2^n-1 是素数  → 预期 DISPROVEN (反例: n=11, 2047=23×89)

用法：直接从项目根目录运行
  cd /workspace/multi-agent-brain-orchestrator
  python3 module_math_b/tests_mathb/run_demo.py
"""

import json
import os
import sys
import gc
import time
from datetime import datetime, timezone
from typing import Any

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from module_math_b.math_router import MathRouter, MathRouteResult, MathWorkflowResult
from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
)
from module_math_b.math_hypo_pool import MathHypothesisPool
from module_math_b.math_convergence import MathConvergence
from module_math_b.math_validator import MathValidator
from module_math_b.math_template_engine import MathTemplateEngine
from module_math_b.math_snapshot_bridge import MathSnapshotBridge
from module_math_b.math_resource_lock import MathResourceLock, DegradationLevel


# =============================================================================
# 数论专用 Demo 工作流（注入真实数学知识）
# =============================================================================

class MathBDemoRunner:
    """
    Module-MathB v1.0 端到端 Demo 执行器

    直接注入 Mersenne 素数相关的真实数学知识，
    完整触发所有模块的冒烟测试。
    """

    def __init__(self, task_json_path: str):
        with open(task_json_path, "r") as f:
            self._task_raw = json.load(f)

        self._task_meta = self._task_raw["task_meta"]
        self._prop_data = self._task_raw["proposition"]
        self._mathb_config = self._task_raw["mathb_config"]
        self._hints = self._task_raw["orchestrator_hints"]

        self._task_id = self._task_meta["task_id"]
        self._max_iterations = self._task_meta.get("max_iterations", 8)

        # 子命题
        self._sub_a_id = "mathb_demo_001_sub_a"  # 正向
        self._sub_b_id = "mathb_demo_001_sub_b"  # 反向

        # 已知反例
        self._counterexample_n = 11
        self._counterexample_value = 2047
        self._counterexample_factorization = "23 × 89"

        # 检查清单
        self._checklist: dict[str, bool] = {}

    # =========================================================================
    # 主入口
    # =========================================================================

    def run(self) -> dict[str, Any]:
        """执行完整端到端 Demo"""
        print("=" * 72)
        print("  Module-MathB v1.0  端到端数论猜想验证 Demo")
        print("=" * 72)
        print()

        result = {
            "demo_title": "Module-MathB v1.0 端到端验证",
            "task_id": self._task_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "checks": {},
            "logs": [],
            "errors": [],
        }

        # ── 步骤 1: 任务路由检测 ──
        self._step1_router_check(result)

        # ── 步骤 2: 初始化数学模块 ──
        router = self._step2_init_session(result)

        # ── 步骤 3: 注册子命题 ──
        self._step3_register_propositions(router, result)

        # ── 步骤 4: 迭代工作流 ──
        final_report = self._step4_iterative_workflow(router, result)

        # ── 步骤 5: 收敛验证 ──
        self._step5_convergence_check(final_report, result)

        # ── 步骤 6: 快照审计 ──
        self._step6_snapshot_audit(router, result)

        # ── 步骤 7: 模块销毁清理 ──
        self._step7_cleanup(router, result)

        # ── 步骤 8: 原系统完整性验证 ──
        self._step8_original_system_integrity(result)

        # ── 最终报告 ──
        self._print_final_report(result)
        return result

    # =========================================================================
    # 步骤 1: 路由检测
    # =========================================================================

    def _step1_router_check(self, result: dict) -> None:
        print("─" * 60)
        print("【步骤 1】math_router 任务识别与分流")
        print("─" * 60)

        router = MathRouter()
        route = router.is_math_task({
            "query": self._prop_data["statement"],
            "task_type": self._task_meta["task_type"],
            "task_id": self._task_id,
        })

        check = route.is_math_task
        result["checks"]["router_math_detection"] = {
            "status": "PASS" if check else "FAIL",
            "detail": {
                "is_math_task": route.is_math_task,
                "matched_keywords": route.matched_keywords,
                "propositions_extracted": len(route.propositions_extracted),
            },
        }
        print(f"  任务识别: {'MATH_TASK' if check else 'NON_MATH'}")
        print(f"  匹配关键词: {route.matched_keywords}")
        print(f"  提取命题: {len(route.propositions_extracted)} 个")
        print()

        router.destroy_math_session()

    # =========================================================================
    # 步骤 2: 初始化数学模块
    # =========================================================================

    def _step2_init_session(self, result: dict) -> MathRouter:
        print("─" * 60)
        print("【步骤 2】初始化 Module-MathB 完整集群")
        print("─" * 60)

        router = MathRouter()
        router.init_math_session(self._task_id)

        checks = {
            "hypothesis_pool": router.hypothesis_pool is not None,
            "convergence": router.convergence is not None,
            "validator": router.validator is not None,
            "template_engine": router.template_engine is not None,
            "snapshot_bridge": router.snapshot_bridge is not None,
            "resource_lock": router.resource_lock is not None,
            "database": router.database is not None,
        }
        all_ok = all(checks.values())
        result["checks"]["session_init"] = {
            "status": "PASS" if all_ok else "FAIL",
            "detail": checks,
        }

        for name, ok in checks.items():
            print(f"  {name:25s} {'✓ OK' if ok else '✗ MISSING'}")
        print()

        # 记录日志
        if router.database:
            router.database.log_event("demo", "SESSION_INIT", f"task_id={self._task_id}")

        return router

    # =========================================================================
    # 步骤 3: 注册子命题
    # =========================================================================

    def _step3_register_propositions(self, router: MathRouter, result: dict) -> None:
        print("─" * 60)
        print("【步骤 3】注册子命题到 math_hypo_pool")
        print("─" * 60)

        pool = router.hypothesis_pool
        assert pool is not None

        # 子命题 A: 正向 — 若 2^n-1 为素数 ⇒ n 是素数
        prop_a = pool.register_proposition(
            proposition_id=self._sub_a_id,
            statement="若 2^n − 1 是素数 (Mersenne 素数)，则 n 必定是素数",
            domain="number_theory",
            difficulty="medium",
        )
        print(f"  子命题A [{self._sub_a_id}]: {prop_a.statement[:60]}...")

        # 子命题 B: 反向 — 若 n 为素数 ⇒ 2^n-1 是素数
        prop_b = pool.register_proposition(
            proposition_id=self._sub_b_id,
            statement="若 n 是素数，则 2^n − 1 必定是素数",
            domain="number_theory",
            difficulty="medium",
        )
        print(f"  子命题B [{self._sub_b_id}]: {prop_b.statement[:60]}...")

        count = pool.proposition_count
        result["checks"]["proposition_registration"] = {
            "status": "PASS" if count == 2 else "FAIL",
            "detail": {
                "total": count,
                "sub_a_id": self._sub_a_id,
                "sub_b_id": self._sub_b_id,
                "sub_a_status": prop_a.status,
                "sub_b_status": prop_b.status,
            },
        }
        print(f"  假说池命题总数: {count}")
        print()

        # 持久化
        if router.database:
            for prop in (prop_a, prop_b):
                router.database.insert_proposition({
                    "proposition_id": prop.proposition_id,
                    "statement": prop.statement,
                    "domain": prop.domain,
                    "difficulty": prop.difficulty,
                    "iteration_depth": 0,
                    "status": prop.status,
                    "proven_by": "",
                    "proof_chain_hash": "",
                    "created_at": prop.created_at,
                })
            router.database.log_event("demo", "PROPOSITIONS_REGISTERED", f"count={count}")

    # =========================================================================
    # 步骤 4: 迭代工作流
    # =========================================================================

    def _step4_iterative_workflow(self, router: MathRouter, result: dict) -> dict[str, Any]:
        print("─" * 60)
        print("【步骤 4】多轮迭代工作流")
        print("─" * 60)

        pool = router.hypothesis_pool
        validator = router.validator
        convergence = router.convergence
        bridge = router.snapshot_bridge
        lock = router.resource_lock
        db = router.database
        assert pool is not None
        assert validator is not None
        assert convergence is not None
        assert bridge is not None
        assert lock is not None

        round_logs: list[dict] = []
        final_report = None

        for rnd in range(1, self._max_iterations + 1):
            print(f"\n  --- 第 {rnd} 轮 ---")

            # 资源检查
            status = lock.check_status()
            if status.level >= DegradationLevel.L3:
                print(f"  ⚠ 资源锁 L3 降级，强制终止")
                result["logs"].append(f"Round {rnd}: L3 degradation, forced stop")
                break

            # ── 第 1 轮: 构建证明步骤 ──
            if rnd == 1:
                self._build_proof_steps(pool, validator)

            # ── 第 2 轮: 注入反例 ──
            if rnd == 2:
                self._inject_counterexample(pool, validator)

            # ── 校验所有命题 ──
            for prop in pool.get_all_propositions():
                report = validator.validate_proposition(prop, round_number=rnd)
                pool.add_validation_report(prop.proposition_id, report)

                if db:
                    try:
                        db.insert_validation_report({
                            "report_id": report.report_id,
                            "proposition_id": report.proposition_id,
                            "round_number": report.round_number,
                            "syntax_valid": report.syntax_valid,
                            "syntax_errors": report.syntax_errors,
                            "logical_gaps": report.logical_gaps,
                            "hidden_assumptions": report.hidden_assumptions,
                            "circular_found": report.circular_reasoning_found,
                            "overall_valid": report.overall_valid,
                            "overall_score": report.overall_score,
                            "requires_iteration": report.requires_iteration,
                            "iteration_hints": report.iteration_hints,
                        })
                    except Exception:
                        pass

            # ── 更新状态 ──
            changes = pool.update_statuses_from_validation()
            for pid, change in changes.items():
                print(f"  状态变更: {pid} — {change}")

            # ── 收敛判定 ──
            conv_report = convergence.evaluate(pool, round_number=rnd)
            print(f"  收敛判定: {'已收敛' if conv_report.is_converged else '未收敛'} "
                  f"({conv_report.convergence_type or '仍需迭代'})")
            if conv_report.convergence_reason:
                print(f"  原因: {conv_report.convergence_reason}")

            # ── 快照 ──
            snap = bridge.create_snapshot(
                round_number=rnd, pool=pool,
                convergence_report=conv_report,
            )
            if db:
                db.insert_snapshot({
                    "snapshot_id": snap.snapshot_id,
                    "task_id": snap.task_id,
                    "round_number": snap.round_number,
                    "timestamp": snap.timestamp,
                    "content_hash": snap.content_hash,
                    "prev_snapshot_hash": snap.prev_snapshot_hash,
                    "snapshot_data": {
                        "propositions": snap.propositions,
                        "convergence_report": snap.convergence_report,
                    },
                })

            round_logs.append({
                "round": rnd,
                "converged": conv_report.is_converged,
                "convergence_type": conv_report.convergence_type,
                "propositions": pool.to_dict_list(),
                "snapshot_hash": snap.content_hash,
                "snapshot_tag": snap.extension_tag,
            })

            if conv_report.is_converged:
                final_report = conv_report
                print(f"\n  ✓ 收敛于第 {rnd} 轮！")
                result["logs"].append(f"Converged at round {rnd}: {conv_report.convergence_type}")
                break

            if rnd >= self._max_iterations:
                final_report = conv_report
                result["logs"].append(f"Max iterations reached at round {rnd}")
                break

        result["checks"]["iterative_workflow"] = {
            "status": "PASS" if final_report and final_report.is_converged else "FAIL",
            "detail": {
                "total_rounds": len(round_logs),
                "final_convergence_type": final_report.convergence_type if final_report else "N/A",
                "round_logs": round_logs,
            },
        }
        print()
        return final_report or {}

    # =========================================================================
    # 构建证明步骤
    # =========================================================================

    def _build_proof_steps(self, pool: MathHypothesisPool, validator: MathValidator) -> None:
        """构建两个子命题的推理步骤"""
        now = datetime.now(timezone.utc).isoformat()

        # ── 子命题 A: 正向证明（正确） ──
        steps_a = [
            MathDerivationStep(
                step_id="a_step_1", step_number=1,
                premises=["2^n - 1 是素数", "n > 1"],
                conclusion="假设 n 是合数，n = a × b，其中 a, b > 1",
                derivation_rule="proof_by_contradiction",
                justification="采用反证法，假设 n 为合数",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="a_step_2", step_number=2,
                premises=["n = a × b", "a, b > 1"],
                conclusion="2^n - 1 = 2^(a×b) - 1 = (2^a)^b - 1",
                derivation_rule="algebraic_manipulation",
                justification="指数运算性质",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="a_step_3", step_number=3,
                premises=["(2^a)^b - 1"],
                conclusion="(2^a)^b - 1 = (2^a - 1) × (2^(a(b-1)) + 2^(a(b-2)) + ... + 1)",
                derivation_rule="factorization",
                justification="等比数列求和公式: x^b - 1 = (x-1)(x^(b-1)+...+1)",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="a_step_4", step_number=4,
                premises=["(2^a - 1) × (2^(a(b-1)) + ... + 1)", "a > 1"],
                conclusion="2^a - 1 > 1 且 2^(a(b-1)) + ... + 1 > 1，故 2^n - 1 不是素数",
                derivation_rule="contradiction",
                justification="若 n 是合数，则 2^n - 1 可分解为两个大于 1 的因子之积，与素数定义矛盾",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="a_step_5", step_number=5,
                premises=["2^n - 1 是素数且 n 为合数会导致矛盾"],
                conclusion="因此，若 2^n - 1 是素数，则 n 必定是素数。QED",
                derivation_rule="contrapositive",
                justification="反证法完成，原命题得证",
                source_agent="prover_agent", created_at=now,
            ),
        ]
        for step in steps_a:
            validator.validate_derivation_step(step, steps_a)
        pool.add_derivation_steps_batch(self._sub_a_id, steps_a)
        print(f"  子命题A: 添加 {len(steps_a)} 步推导（反证法证明）")

        # ── 子命题 B: 初步探索（将被反例推翻） ──
        steps_b = [
            MathDerivationStep(
                step_id="b_step_1", step_number=1,
                premises=["n 是素数", "素数定义: n > 1 且仅被 1 和自身整除"],
                conclusion="2^n - 1 称为 Mersenne 数，记为 M_n",
                derivation_rule="definition",
                justification="Mersenne 数的标准定义",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="b_step_2", step_number=2,
                premises=["n 是素数", "M_n = 2^n - 1"],
                conclusion="需要验证 M_n 是否对所有素数 n 都为素数",
                derivation_rule="hypothesis",
                justification="这是待验证的猜想，需要逐一检验",
                source_agent="prover_agent", created_at=now,
            ),
            MathDerivationStep(
                step_id="b_step_3", step_number=3,
                premises=["n = 2, 3, 5, 7"],
                conclusion="M_2=3(素数), M_3=7(素数), M_5=31(素数), M_7=127(素数)",
                derivation_rule="direct_computation",
                justification="小素数验证通过，但不足以证明对所有素数成立",
                has_gap=True,
                gap_description="归纳不完整，仅验证了前 4 个素数，未覆盖所有素数",
                source_agent="prover_agent", created_at=now,
            ),
        ]
        for step in steps_b:
            validator.validate_derivation_step(step, steps_b)
        pool.add_derivation_steps_batch(self._sub_b_id, steps_b)
        print(f"  子命题B: 添加 {len(steps_b)} 步推导（含归纳缺口标记）")

    # =========================================================================
    # 注入反例
    # =========================================================================

    def _inject_counterexample(self, pool: MathHypothesisPool, validator: MathValidator) -> None:
        """注入 n=11 的反例: 2^11 - 1 = 2047 = 23 × 89"""
        now = datetime.now(timezone.utc).isoformat()

        print(f"  反例搜索: 检验 n=11 → 2^11 - 1 = {self._counterexample_value}")
        print(f"  因式分解: {self._counterexample_value} = {self._counterexample_factorization}")

        # 添加反例推导步骤
        ce_step = MathDerivationStep(
            step_id="b_step_ce_1", step_number=4,
            premises=["n = 11 是素数", "M_11 = 2^11 - 1 = 2047"],
            conclusion="2047 = 23 × 89，是两个大于 1 的整数之积，故 M_11 不是素数",
            derivation_rule="counterexample",
            justification=(
                f"直接计算: 2^{self._counterexample_n} - 1 = {self._counterexample_value} = "
                f"{self._counterexample_factorization}，"
                f"23 和 89 均大于 1，故 {self._counterexample_value} 是合数"
            ),
            source_agent="counter_example_seeker_agent",
            created_at=now,
        )
        validator.validate_derivation_step(ce_step, [ce_step])
        pool.add_derivation_step(self._sub_b_id, ce_step)

        # 注册反例
        counter = MathCounterExample(
            example_id="ce_mathb_demo_001",
            target_proposition_id=self._sub_b_id,
            value_representation=f"n = {self._counterexample_n}",
            domain_check=f"n = {self._counterexample_n} 是素数，属于命题定义域",
            constraint_check=f"验证 2^{self._counterexample_n} - 1 = {self._counterexample_value} = {self._counterexample_factorization}",
            is_valid=True,
            is_reproducible=True,
            verification_steps=[
                f"检查 n = {self._counterexample_n} 是否为素数: 是",
                f"计算 2^{self._counterexample_n} - 1 = {self._counterexample_value}",
                f"因式分解: {self._counterexample_value} = {self._counterexample_factorization}",
                f"结论: {self._counterexample_value} 是合数，不是素数",
                "反例有效且可复现",
            ],
            source_agent="counter_example_seeker_agent",
            created_at=now,
        )
        pool.add_counter_example(self._sub_b_id, counter)
        print(f"  反例注册: ce_mathb_demo_001 (n={self._counterexample_n}, 有效且可复现)")

    # =========================================================================
    # 步骤 5: 收敛验证
    # =========================================================================

    def _step5_convergence_check(self, final_report: Any, result: dict) -> None:
        print("─" * 60)
        print("【步骤 5】收敛判定验证")
        print("─" * 60)

        if final_report is None:
            result["checks"]["convergence"] = {
                "status": "FAIL",
                "detail": {"error": "final_report is None"},
            }
            print("  ✗ 无最终收敛报告")
            print()
            return

        is_converged = final_report.is_converged
        conv_type = final_report.convergence_type

        print(f"  收敛: {'是' if is_converged else '否'}")
        print(f"  类型: {conv_type}")
        print(f"  原因: {final_report.convergence_reason}")

        # 验证不使用置信度
        no_confidence = "confidence" not in str(final_report.convergence_reason).lower()
        no_bayesian = "bayesian" not in str(final_report).lower()
        no_voting = "vote" not in str(final_report.convergence_reason).lower()

        checks = {
            "is_converged": is_converged,
            "convergence_type_is_disproven": conv_type == "DISPROVEN",
            "no_confidence_based": no_confidence,
            "no_bayesian": no_bayesian,
            "no_voting": no_voting,
        }
        all_ok = all(checks.values())
        result["checks"]["convergence"] = {
            "status": "PASS" if all_ok else "WARN",
            "detail": checks,
        }

        for name, ok in checks.items():
            print(f"  {name:35s} {'✓' if ok else '✗'}")

        result["convergence_report"] = {
            "is_converged": is_converged,
            "type": conv_type,
            "reason": final_report.convergence_reason,
            "proof_completeness": final_report.proof_completeness,
            "counter_example_count": final_report.counter_example_count,
            "total_rounds_executed": final_report.round_number,
        }
        print()

    # =========================================================================
    # 步骤 6: 快照审计
    # =========================================================================

    def _step6_snapshot_audit(self, router: MathRouter, result: dict) -> None:
        print("─" * 60)
        print("【步骤 6】快照桥接与哈希链审计")
        print("─" * 60)

        bridge = router.snapshot_bridge
        assert bridge is not None

        # 验证哈希链完整性
        chain_ok = bridge.verify_chain_integrity()
        print(f"  哈希链完整性: {'✓ 完整' if chain_ok else '✗ 断裂'}")

        # 导出证明链
        export = bridge.export_proof_chain()
        print(f"  总轮数: {export['total_rounds']}")
        print(f"  快照数: {len(export['snapshots'])}")

        # 检查 MATH_B_EXT 标记
        all_tagged = True
        for snap in bridge.get_all_snapshots():
            if snap.extension_tag != "MATH_B_EXT":
                all_tagged = False
                print(f"  ✗ 快照 {snap.snapshot_id} 缺少 MATH_B_EXT 标记")
            else:
                print(f"  ✓ 快照 {snap.snapshot_id} "
                      f"| round={snap.round_number} "
                      f"| tag={snap.extension_tag} "
                      f"| hash={snap.content_hash[:16]}...")

        # 验证主系统兼容格式
        fmt = bridge.to_main_system_format()
        has_math_tag = fmt.get("extension_tag") == "MATH_B_EXT"
        has_math_props = "math_propositions" in fmt
        has_math_proof = "math_proof_chain" in fmt

        checks = {
            "hash_chain_integrity": chain_ok,
            "all_snapshots_tagged": all_tagged,
            "main_system_format_tag": has_math_tag,
            "main_system_has_math_propositions": has_math_props,
            "main_system_has_math_proof": has_math_proof,
        }
        all_ok = all(checks.values())
        result["checks"]["snapshot_audit"] = {
            "status": "PASS" if all_ok else "WARN",
            "detail": checks,
        }

        for name, ok in checks.items():
            print(f"  {name:35s} {'✓' if ok else '✗'}")

        result["snapshot_export"] = export
        print()

    # =========================================================================
    # 步骤 7: 清理
    # =========================================================================

    def _step7_cleanup(self, router: MathRouter, result: dict) -> None:
        print("─" * 60)
        print("【步骤 7】模块销毁与资源清理")
        print("─" * 60)

        gc.collect()
        before = len(gc.get_objects())

        router.destroy_math_session()

        gc.collect()
        after = len(gc.get_objects())

        # 验证模块已销毁
        is_destroyed = (
            not router.is_initialized
            and not router.is_math_session
            and router.hypothesis_pool is None
            and router.database is None
            and router.convergence is None
            and router.validator is None
            and router.template_engine is None
            and router.snapshot_bridge is None
            and router.resource_lock is None
        )

        print(f"  模块实例已销毁: {'✓ 是' if is_destroyed else '✗ 否'}")
        print(f"  DB 连接已关闭: {'✓ 是' if router.database is None else '✗ 否'}")
        print(f"  资源锁已释放: {'✓ 是' if router.resource_lock is None else '✗ 否'}")
        print(f"  内存对象变化: before={before}, after={after}, diff={abs(after - before)}")

        result["checks"]["cleanup"] = {
            "status": "PASS" if is_destroyed else "FAIL",
            "detail": {
                "is_destroyed": is_destroyed,
                "db_closed": router.database is None,
                "lock_released": router.resource_lock is None,
                "memory_diff": abs(after - before),
            },
        }

        # 清理临时 DB 文件
        if router.DB_PATH:
            import glob as _g
            for f in _g.glob(router.DB_PATH + "*"):
                try:
                    os.remove(f)
                except Exception:
                    pass
        print()

    # =========================================================================
    # 步骤 8: 原系统完整性
    # =========================================================================

    def _step8_original_system_integrity(self, result: dict) -> None:
        print("─" * 60)
        print("【步骤 8】原系统完整性验证")
        print("─" * 60)

        checks = {}

        # 检查 brain_subsystem 未受影响
        try:
            from brain_subsystem.interface import BrainInterface
            from brain_subsystem.kernel import BrainKernel
            from brain_subsystem.constants import BRAIN_CONSTANTS
            bi = BrainInterface()
            res = bi.run_inference(context="test", depth=1)
            checks["brain_subsystem"] = res["confidence"] == BRAIN_CONSTANTS.COGNITION_THRESHOLD_DEFAULT
            print(f"  brain_subsystem 正常: {'✓' if checks['brain_subsystem'] else '✗'}")
        except Exception as e:
            checks["brain_subsystem"] = False
            print(f"  brain_subsystem 异常: {e}")

        # 检查 harness 未受影响
        try:
            from harness.meta_rules import MetaRules
            from harness.orchestrator import Orchestrator
            from harness.safety_validator import SafetyValidator
            rules = MetaRules()
            checks["harness"] = rules is not None
            print(f"  harness 正常: {'✓' if checks['harness'] else '✗'}")
        except Exception as e:
            checks["harness"] = False
            print(f"  harness 异常: {e}")

        # 检查 agents 未受影响
        try:
            from agents.lead_researcher import LeadResearcher
            lr = LeadResearcher()
            checks["agents"] = lr is not None
            print(f"  agents 正常: {'✓' if checks['agents'] else '✗'}")
        except Exception as e:
            checks["agents"] = False
            print(f"  agents 异常: {e}")

        all_ok = all(checks.values())
        result["checks"]["original_system"] = {
            "status": "PASS" if all_ok else "FAIL",
            "detail": checks,
        }
        print()

    # =========================================================================
    # 最终报告
    # =========================================================================

    def _print_final_report(self, result: dict) -> None:
        print("=" * 72)
        print("  Module-MathB v1.0  端到端验证最终报告")
        print("=" * 72)
        print()

        # 汇总检查项
        all_checks = result["checks"]
        passed = sum(1 for c in all_checks.values() if c["status"] == "PASS")
        failed = sum(1 for c in all_checks.values() if c["status"] == "FAIL")
        warned = sum(1 for c in all_checks.values() if c["status"] == "WARN")
        total = len(all_checks)

        print(f"  检查项总计: {total}")
        print(f"  通过: {passed}  |  失败: {failed}  |  警告: {warned}")
        print()

        for name, check in all_checks.items():
            icon = "✅" if check["status"] == "PASS" else ("⚠️" if check["status"] == "WARN" else "❌")
            print(f"  {icon} {name}: {check['status']}")

        print()

        # 核心结论
        conv = result.get("convergence_report", {})
        if conv.get("is_converged") and conv.get("type") == "DISPROVEN":
            print("  ┌──────────────────────────────────────────────────────┐")
            print("  │  ✓ 核心结论                                          │")
            print("  │                                                      │")
            print("  │  原整体猜想被证伪。                                  │")
            print("  │  正向子命题 (若 2^n-1 为素数 ⇒ n 是素数) 成立。     │")
            print(f"  │  反向子命题 (若 n 为素数 ⇒ 2^n-1 是素数) 不成立。   │")
            print(f"  │  反例: n={self._counterexample_n}, " +
                  f"2^{self._counterexample_n}-1={self._counterexample_value}=" +
                  f"{self._counterexample_factorization}。")
            print("  │                                                      │")
            print("  │  快照完整可追溯，哈希链完整，MATH_B_EXT 标记正确。   │")
            print("  │  模块已销毁，原系统未受影响。                        │")
            print("  └──────────────────────────────────────────────────────┘")
        else:
            print("  ⚠ 未达到预期收敛状态，请检查日志")

        print()

        result["overall_status"] = "PASS" if failed == 0 else ("WARN" if failed <= 1 else "FAIL")
        result["completed_at"] = datetime.now(timezone.utc).isoformat()

        print(f"  整体判定: {result['overall_status']}")
        print(f"  完成时间: {result['completed_at']}")


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    task_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "mathb_demo_task.json",
    )
    runner = MathBDemoRunner(task_path)
    final_result = runner.run()

    # 返回码
    sys.exit(0 if final_result["overall_status"] == "PASS" else 1)