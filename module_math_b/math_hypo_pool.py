"""
module_math_b.math_hypo_pool — 数学专用四态证明假说池

完全废弃贝叶斯统计逻辑，采用纯逻辑二态判定体系。
数学唯一合法四态：
  PENDING       — 待严格推导验证
  PROVEN        — 已获得严谨证明
  DISPROVEN     — 已存在有效反例
  INCONCLUSIVE  — 证据不足无法判定

核心规则：
  1. 每条数学命题只看逻辑有效性、推导完整性、反例存在性
  2. 禁止「多 Agent 共识 = 正确」的错误科研逻辑
  3. 严格记录：引理缺口、逻辑跳跃、未定义前提、循环论证
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
)


@dataclass
class PoolSnapshot:
    """假说池快照"""
    active_count: int
    proven_count: int
    disproven_count: int
    inconclusive_count: int
    pending_count: int
    round_number: int
    proposition_ids: list[str] = field(default_factory=list)


# =============================================================================
# 数学假说池
# =============================================================================

class MathHypothesisPool:
    """
    数学专用四态假说池

    与主系统 HypothesisPool 完全独立：
      - 不共享任何数据结构
      - 不共享任何内存
      - 不共享任何收敛逻辑
      - 纯逻辑判定，零概率/零统计
    """

    __slots__ = ("_propositions", "_lock")

    def __init__(self) -> None:
        import threading
        self._propositions: dict[str, MathProposition] = {}
        self._lock = threading.Lock()

    # =========================================================================
    # 命题管理
    # =========================================================================

    def register_proposition(
        self,
        proposition_id: str,
        statement: str,
        domain: str = "number_theory",
        difficulty: str = "intermediate",
    ) -> MathProposition:
        """
        注册新数学命题

        所有命题初始状态为 PENDING。
        """
        now = datetime.now(timezone.utc).isoformat()
        prop = MathProposition(
            proposition_id=proposition_id,
            statement=statement,
            domain=domain,  # type: ignore[arg-type]
            difficulty=difficulty,  # type: ignore[arg-type]
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._propositions[proposition_id] = prop
        return prop

    def register_from_worker_outputs(
        self, worker_outputs: dict[str, Any], round_number: int = 1
    ) -> list[MathProposition]:
        """
        从 Worker 输出中提取并注册命题

        解析各 Agent 输出中的 propositions 字段。
        """
        registered: list[MathProposition] = []
        for agent_id, output in worker_outputs.items():
            inner = output.get("output", output)
            if not isinstance(inner, dict):
                continue
            propositions = inner.get("propositions", [])
            if not isinstance(propositions, list):
                continue
            for p_data in propositions:
                if not isinstance(p_data, dict):
                    continue
                pid = p_data.get("proposition_id", p_data.get("id", ""))
                if not pid or pid in self._propositions:
                    continue
                prop = self.register_proposition(
                    proposition_id=pid,
                    statement=p_data.get("statement", p_data.get("description", "")),
                    domain=p_data.get("domain", "number_theory"),
                    difficulty=p_data.get("difficulty", "intermediate"),
                )
                prop.iteration_depth = round_number
                registered.append(prop)
        return registered

    # =========================================================================
    # 推导步骤管理
    # =========================================================================

    def add_derivation_step(
        self, proposition_id: str, step: MathDerivationStep
    ) -> bool:
        """
        向命题添加推导步骤

        自动检测逻辑完整性并标记。
        """
        with self._lock:
            prop = self._propositions.get(proposition_id)
            if prop is None:
                return False
            prop.derivation_steps.append(step)
            prop.updated_at = datetime.now(timezone.utc).isoformat()
            return True

    def add_derivation_steps_batch(
        self, proposition_id: str, steps: list[MathDerivationStep]
    ) -> int:
        """批量添加推导步骤"""
        count = 0
        for step in steps:
            if self.add_derivation_step(proposition_id, step):
                count += 1
        return count

    # =========================================================================
    # 反例管理
    # =========================================================================

    def add_counter_example(
        self, proposition_id: str, counter: MathCounterExample
    ) -> bool:
        """
        向命题添加反例候选

        只有 is_valid=True 且 is_reproducible=True 的反例才有效。
        """
        with self._lock:
            prop = self._propositions.get(proposition_id)
            if prop is None:
                return False
            prop.counter_examples.append(counter)
            prop.updated_at = datetime.now(timezone.utc).isoformat()
            return True

    def has_valid_counter_example(self, proposition_id: str) -> bool:
        """检查是否存在有效反例"""
        prop = self._propositions.get(proposition_id)
        if prop is None:
            return False
        return any(
            ce.is_valid and ce.is_reproducible
            for ce in prop.counter_examples
        )

    # =========================================================================
    # 校验报告管理
    # =========================================================================

    def add_validation_report(
        self, proposition_id: str, report: MathValidationReport
    ) -> bool:
        """添加校验报告"""
        with self._lock:
            prop = self._propositions.get(proposition_id)
            if prop is None:
                return False
            prop.validation_reports.append(report)
            prop.updated_at = datetime.now(timezone.utc).isoformat()
            return True

    # =========================================================================
    # 状态更新
    # =========================================================================

    def update_proposition_status(
        self,
        proposition_id: str,
        status: Literal["PENDING", "PROVEN", "DISPROVEN", "INCONCLUSIVE"],
        proven_by: str = "",
        proof_hash: str = "",
    ) -> bool:
        """
        更新命题状态

        核心规则：
          - 只有无断层/无跳跃/无循环/无隐性假设的完整证明 → PROVEN
          - 只有存在有效反例 → DISPROVEN
          - 禁止多人共识改状态
        """
        with self._lock:
            prop = self._propositions.get(proposition_id)
            if prop is None:
                return False
            prop.status = status
            prop.proven_by = proven_by
            prop.proof_chain_hash = proof_hash
            prop.updated_at = datetime.now(timezone.utc).isoformat()
            return True

    def update_statuses_from_validation(self) -> dict[str, str]:
        """
        根据校验报告自动更新命题状态

        遍历所有命题，根据推导步骤和校验报告判定状态。
        """
        status_changes: dict[str, str] = {}
        with self._lock:
            for pid, prop in self._propositions.items():
                if prop.status in ("PROVEN", "DISPROVEN"):
                    continue  # 已终态，不再改

                old_status = prop.status

                # 检查是否有有效反例
                if self.has_valid_counter_example(pid):
                    prop.status = "DISPROVEN"
                    status_changes[pid] = f"{old_status} -> DISPROVEN"
                    continue

                # 检查是否有完整证明
                if self._is_proof_complete(prop):
                    prop.status = "PROVEN"
                    status_changes[pid] = f"{old_status} -> PROVEN"
                    continue

                # 检查是否有进展
                if not prop.derivation_steps:
                    status_changes[pid] = f"{old_status} -> INCONCLUSIVE"
                    prop.status = "INCONCLUSIVE"

        return status_changes

    def _is_proof_complete(self, prop: MathProposition) -> bool:
        """
        判定证明是否完整

        必要条件：
          1. 至少有一个推导步骤
          2. 所有步骤无 gap
          3. 所有步骤无 hidden_assumption
          4. 所有步骤无 circular
          5. 所有步骤 validation_passed
          6. 至少有一个校验报告 overall_valid=True
        """
        if not prop.derivation_steps:
            return False

        for step in prop.derivation_steps:
            if step.has_gap:
                return False
            if step.has_hidden_assumption:
                return False
            if step.is_circular:
                return False
            if not step.validation_passed:
                return False

        # 至少有一个校验报告确认整体有效
        if not prop.validation_reports:
            return False
        return any(r.overall_valid for r in prop.validation_reports)

    # =========================================================================
    # 查询
    # =========================================================================

    def get_proposition(self, proposition_id: str) -> MathProposition | None:
        return self._propositions.get(proposition_id)

    def get_all_propositions(self) -> list[MathProposition]:
        return list(self._propositions.values())

    def get_propositions_by_status(
        self, status: str
    ) -> list[MathProposition]:
        return [
            p for p in self._propositions.values() if p.status == status
        ]

    def snapshot(self) -> PoolSnapshot:
        """获取假说池快照"""
        proven = sum(1 for p in self._propositions.values() if p.status == "PROVEN")
        disproven = sum(1 for p in self._propositions.values() if p.status == "DISPROVEN")
        inconclusive = sum(1 for p in self._propositions.values() if p.status == "INCONCLUSIVE")
        pending = sum(1 for p in self._propositions.values() if p.status == "PENDING")
        return PoolSnapshot(
            active_count=proven + disproven + pending,  # INCONCLUSIVE 不算活跃
            proven_count=proven,
            disproven_count=disproven,
            inconclusive_count=inconclusive,
            pending_count=pending,
            round_number=0,
            proposition_ids=list(self._propositions.keys()),
        )

    def to_dict_list(self) -> list[dict[str, Any]]:
        """导出为字典列表（用于持久化）"""
        result = []
        for prop in self._propositions.values():
            result.append({
                "proposition_id": prop.proposition_id,
                "statement": prop.statement,
                "domain": prop.domain,
                "difficulty": prop.difficulty,
                "status": prop.status,
                "iteration_depth": prop.iteration_depth,
                "derivation_step_count": len(prop.derivation_steps),
                "counter_example_count": len(prop.counter_examples),
                "valid_counter_example_count": sum(
                    1 for ce in prop.counter_examples if ce.is_valid and ce.is_reproducible
                ),
                "validation_report_count": len(prop.validation_reports),
                "gap_count": sum(1 for s in prop.derivation_steps if s.has_gap),
                "circular_count": sum(1 for s in prop.derivation_steps if s.is_circular),
                "hidden_assumption_count": sum(
                    1 for s in prop.derivation_steps if s.has_hidden_assumption
                ),
                "proven_by": prop.proven_by,
                "proof_chain_hash": prop.proof_chain_hash,
                "created_at": prop.created_at,
                "updated_at": prop.updated_at,
            })
        return result

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def proposition_count(self) -> int:
        return len(self._propositions)

    @property
    def proven_count(self) -> int:
        return sum(1 for p in self._propositions.values() if p.status == "PROVEN")

    @property
    def disproven_count(self) -> int:
        return sum(1 for p in self._propositions.values() if p.status == "DISPROVEN")

    def clear(self) -> None:
        """清空假说池"""
        with self._lock:
            self._propositions.clear()