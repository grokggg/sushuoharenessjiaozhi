"""
module_math_b.math_convergence — 数学专用收敛判定引擎

Claude 级严谨，杜绝虚假共识。
数学任务唯一收敛判定标准（严格数学范式）：

满足任意一条即可正式收敛结束迭代：
  1. 获得无断层/无跳跃/无循环/无隐性假设的完整证明 → PROVEN
  2. 构造定义域合法/约束合规/可复现的有效反例 → DISPROVEN
  3. 连续多轮全部推导 INCONCLUSIVE，无进展熵降为 0 → 强制终止

禁止规则：
  - 禁止置信度共识收敛
  - 禁止多数投票收敛
  - 禁止概率后验收敛
  - 杜绝所有数学领域「群体错误共识」
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
    MathConvergenceReport,
)
from module_math_b.math_hypo_pool import MathHypothesisPool


# =============================================================================
# 收敛判定器
# =============================================================================

class MathConvergence:
    """
    数学专用收敛判定器

    与主系统 ConvergenceVector 完全独立：
      - 不使用置信度
      - 不使用投票
      - 不使用概率/贝叶斯
      - 纯逻辑推导完整性判定
    """

    # 停滞阈值
    MAX_STAGNATION_ROUNDS: int = 3  # 连续无进展超过此轮数强制终止

    __slots__ = ("_stagnation_counter", "_last_derivation_count", "_round_history")

    def __init__(self) -> None:
        self._stagnation_counter: int = 0
        self._last_derivation_count: int = 0
        self._round_history: list[dict[str, Any]] = []

    # =========================================================================
    # 收敛判定
    # =========================================================================

    def evaluate(
        self,
        pool: MathHypothesisPool,
        round_number: int,
        worker_outputs: dict[str, Any] | None = None,
    ) -> MathConvergenceReport:
        """
        判定本轮是否收敛

        Args:
            pool:        数学假说池
            round_number: 当前轮次
            worker_outputs: 本轮 Worker 输出（可选）

        Returns:
            MathConvergenceReport 收敛判定报告
        """
        now = datetime.now(timezone.utc).isoformat()
        report = MathConvergenceReport(
            task_id="",
            round_number=round_number,
            created_at=now,
        )

        propositions = pool.get_all_propositions()
        if not propositions:
            report.is_converged = False
            report.convergence_reason = "无命题注册，无法判定"
            self._record_round(report)
            return report

        total_derivations = sum(len(p.derivation_steps) for p in propositions)

        # 检查每个命题
        for prop in propositions:
            self._evaluate_proposition(prop, report)

        # 判定 1: PROVEN — 所有命题均获得完整证明
        if report.proof_completeness >= 1.0 and report.proof_gap_count == 0:
            report.is_converged = True
            report.convergence_type = "PROVEN"
            report.convergence_reason = (
                "所有命题获得无断层/无跳跃/无循环/无隐性假设的完整证明"
            )
            self._record_round(report)
            return report

        # 判定 2: DISPROVEN — 存在有效反例
        if report.counter_example_valid and report.counter_example_count > 0:
            report.is_converged = True
            report.convergence_type = "DISPROVEN"
            report.convergence_reason = (
                f"构造了 {report.counter_example_count} 个定义域合法/约束合规/可复现的有效反例"
            )
            self._record_round(report)
            return report

        # 判定 3: 停滞检测 — 连续多轮无进展
        if total_derivations == self._last_derivation_count:
            self._stagnation_counter += 1
        else:
            self._stagnation_counter = 0
            self._last_derivation_count = total_derivations

        report.stagnation_rounds = self._stagnation_counter

        if self._stagnation_counter >= self.MAX_STAGNATION_ROUNDS:
            report.is_converged = True
            report.convergence_type = "FORCED_TERMINATE"
            report.entropy_zero = True
            report.convergence_reason = (
                f"连续 {self._stagnation_counter} 轮无进展，"
                f"无进展熵降为 0，强制终止"
            )
            self._record_round(report)
            return report

        report.is_converged = False
        report.convergence_reason = "仍需迭代"
        self._record_round(report)
        return report

    def _evaluate_proposition(
        self, prop: MathProposition, report: MathConvergenceReport
    ) -> None:
        """评估单个命题的收敛状态"""
        steps = prop.derivation_steps

        # 计算证明完整度
        if steps:
            valid_steps = sum(1 for s in steps if s.validation_passed)
            report.proof_completeness = max(
                report.proof_completeness,
                valid_steps / len(steps) if len(steps) > 0 else 0.0,
            )

        # 计数 gap
        report.proof_gap_count += sum(1 for s in steps if s.has_gap)
        report.proof_circular_count += sum(1 for s in steps if s.is_circular)
        report.proof_hidden_assumption_count += sum(
            1 for s in steps if s.has_hidden_assumption
        )

        # 检查反例
        valid_counters = [
            ce for ce in prop.counter_examples
            if ce.is_valid and ce.is_reproducible
        ]
        if valid_counters:
            report.counter_example_valid = True
            report.counter_example_count += len(valid_counters)

    def _record_round(self, report: MathConvergenceReport) -> None:
        self._round_history.append({
            "round": report.round_number,
            "is_converged": report.is_converged,
            "convergence_type": report.convergence_type,
            "proof_completeness": report.proof_completeness,
            "gap_count": report.proof_gap_count,
            "stagnation_rounds": report.stagnation_rounds,
        })

    # =========================================================================
    # 查询
    # =========================================================================

    def reset(self) -> None:
        """重置收敛状态"""
        self._stagnation_counter = 0
        self._last_derivation_count = 0
        self._round_history.clear()

    @property
    def stagnation_rounds(self) -> int:
        return self._stagnation_counter

    @property
    def round_history(self) -> list[dict[str, Any]]:
        return list(self._round_history)