"""
module_math_b.math_snapshot_bridge — 数学快照哈希链无损并入主系统

规则：
  1. 数学模块快照独立存储业务数据
  2. 复用主系统哈希链结构，不破坏主审计体系
  3. 每条数学快照标记扩展标识 MATH_B_EXT
  4. 支持全局追溯、单独导出数学全链路证明过程
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from module_math_b.math_structs import MathProofSnapshot
from module_math_b.math_hypo_pool import MathHypothesisPool
from module_math_b.math_convergence import MathConvergenceReport


# =============================================================================
# 快照桥接器
# =============================================================================

class MathSnapshotBridge:
    """
    数学快照桥接器

    生成数学专用快照，提供与主系统哈希链兼容的接口。
    主系统可以通过 extension_tag == "MATH_B_EXT" 识别数学快照。
    """

    __slots__ = ("_snapshots", "_prev_hash", "_task_id")

    def __init__(self, task_id: str = "") -> None:
        self._snapshots: list[MathProofSnapshot] = []
        self._prev_hash: str = ""
        self._task_id: str = task_id

    # =========================================================================
    # 快照创建
    # =========================================================================

    def create_snapshot(
        self,
        round_number: int,
        pool: MathHypothesisPool,
        convergence_report: MathConvergenceReport | None = None,
        validation_summary: dict[str, Any] | None = None,
    ) -> MathProofSnapshot:
        """
        创建数学快照

        快照包含：
          - 假说池中所有命题的完整状态
          - 证明链推导步骤
          - 校验报告摘要
          - 收敛判定报告
          - 哈希链链接
        """
        now = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"math_snap_{self._task_id}_{round_number}"

        # 命题数据
        propositions = pool.to_dict_list()

        # 证明链
        proof_chain: list[dict[str, Any]] = []
        for prop in pool.get_all_propositions():
            for step in prop.derivation_steps:
                proof_chain.append({
                    "step_id": step.step_id,
                    "proposition_id": prop.proposition_id,
                    "step_number": step.step_number,
                    "premises": step.premises,
                    "conclusion": step.conclusion,
                    "derivation_rule": step.derivation_rule,
                    "has_gap": step.has_gap,
                    "is_circular": step.is_circular,
                    "validation_passed": step.validation_passed,
                })

        # 收敛报告
        conv_dict = {}
        if convergence_report:
            conv_dict = {
                "is_converged": convergence_report.is_converged,
                "convergence_type": convergence_report.convergence_type,
                "convergence_reason": convergence_report.convergence_reason,
                "proof_completeness": convergence_report.proof_completeness,
                "proof_gap_count": convergence_report.proof_gap_count,
                "proof_circular_count": convergence_report.proof_circular_count,
                "stagnation_rounds": convergence_report.stagnation_rounds,
            }

        snapshot = MathProofSnapshot(
            snapshot_id=snapshot_id,
            task_id=self._task_id,
            round_number=round_number,
            timestamp=now,
            propositions=propositions,
            proof_chain=proof_chain,
            validation_summary=validation_summary or {},
            convergence_report=conv_dict,
            prev_snapshot_hash=self._prev_hash,
            extension_tag="MATH_B_EXT",
        )

        # 计算内容哈希
        snapshot.content_hash = self._compute_hash(snapshot)
        self._prev_hash = snapshot.content_hash
        self._snapshots.append(snapshot)

        return snapshot

    def _compute_hash(self, snapshot: MathProofSnapshot) -> str:
        """计算快照 SHA-256 哈希"""
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "task_id": snapshot.task_id,
            "round_number": snapshot.round_number,
            "timestamp": snapshot.timestamp,
            "propositions": snapshot.propositions,
            "proof_chain": snapshot.proof_chain,
            "convergence_report": snapshot.convergence_report,
            "prev_snapshot_hash": snapshot.prev_snapshot_hash,
            "extension_tag": snapshot.extension_tag,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    # =========================================================================
    # 查询
    # =========================================================================

    def get_latest_snapshot(self) -> MathProofSnapshot | None:
        if not self._snapshots:
            return None
        return self._snapshots[-1]

    def get_snapshot_by_round(self, round_number: int) -> MathProofSnapshot | None:
        for snap in self._snapshots:
            if snap.round_number == round_number:
                return snap
        return None

    def get_all_snapshots(self) -> list[MathProofSnapshot]:
        return list(self._snapshots)

    def verify_chain_integrity(self) -> bool:
        """
        验证哈希链完整性

        逐一验证每个快照的 prev_snapshot_hash 是否与前一快照的 content_hash 一致。
        """
        for i in range(1, len(self._snapshots)):
            if self._snapshots[i].prev_snapshot_hash != self._snapshots[i - 1].content_hash:
                return False
        return True

    def export_proof_chain(self) -> dict[str, Any]:
        """
        导出完整数学证明链（用于审计）

        Returns:
            {
                "task_id": str,
                "total_rounds": int,
                "chain_verified": bool,
                "snapshots": [...],
                "propositions": [...],
            }
        """
        all_propositions: dict[str, Any] = {}
        for snap in self._snapshots:
            for prop in snap.propositions:
                pid = prop["proposition_id"]
                if pid not in all_propositions:
                    all_propositions[pid] = prop

        return {
            "task_id": self._task_id,
            "total_rounds": len(self._snapshots),
            "chain_verified": self.verify_chain_integrity(),
            "snapshots": [
                {
                    "snapshot_id": s.snapshot_id,
                    "round_number": s.round_number,
                    "timestamp": s.timestamp,
                    "content_hash": s.content_hash,
                    "convergence_report": s.convergence_report,
                }
                for s in self._snapshots
            ],
            "propositions": list(all_propositions.values()),
        }

    def to_main_system_format(self) -> dict[str, Any]:
        """
        转换为主系统兼容的格式

        主系统可以通过 extension_tag == "MATH_B_EXT" 识别数学快照。
        """
        latest = self.get_latest_snapshot()
        if latest is None:
            return {}

        return {
            "archive_id": latest.snapshot_id,
            "task_id": latest.task_id,
            "round_number": latest.round_number,
            "timestamp": latest.timestamp,
            "created_at": latest.timestamp,
            "content_hash": latest.content_hash,
            "prev_archive_hash": latest.prev_snapshot_hash,
            "extension_tag": "MATH_B_EXT",
            "worker_outputs": {},
            "meta_logs": [],
            "convergence_vector": latest.convergence_report,
            "agent_credibility": {},
            "hypothesis_pool_snapshot": {},
            "math_propositions": latest.propositions,
            "math_proof_chain": latest.proof_chain,
            "math_validation_summary": latest.validation_summary,
        }

    def reset(self) -> None:
        self._snapshots.clear()
        self._prev_hash = ""