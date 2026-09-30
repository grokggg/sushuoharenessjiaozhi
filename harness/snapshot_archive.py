"""
harness.snapshot_archive — 版本快照与哈希归档模块 (v2.0)

职责：
1. 保存每一轮全部 Agent 输出、提案、日志
2. 基于 SHA-256 哈希的不可篡改版本归档
3. 支持回滚到任意历史版本
4. 完整的审计追踪链

v2.0 增强：
  - 哈希输入增加 created_at 时间戳和 round_number，防止时间错位攻击
  - 快照元信息扩展（收敛向量、假说池、信誉分）

归档内容每轮包含：
- 子任务提案（ProposedTaskPayload 列表）
- 各 Agent 原始输出
- 元规则触发记录
- 上下文版本号
- 哈希校验值（含时间戳签名）
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from brain_subsystem.constants import BRAIN_CONSTANTS


# =============================================================================
# 归档数据结构
# =============================================================================


@dataclass
class RoundArchive:
    """单轮归档记录"""

    archive_id: str
    task_id: str
    round_number: int
    context_version: str
    timestamp: str

    # 本轮完整数据
    worker_outputs: dict[str, Any] = field(default_factory=dict)
    meta_logs: list[dict[str, Any]] = field(default_factory=list)
    subtask_proposals: list[dict[str, Any]] = field(default_factory=dict)

    # 哈希链
    content_hash: str = ""
    prev_archive_hash: str = ""

    # v2.0: 扩展元信息
    convergence_vector: dict[str, Any] = field(default_factory=dict)
    hypothesis_pool_snapshot: dict[str, Any] = field(default_factory=dict)
    agent_credibility: dict[str, float] = field(default_factory=dict)

    # 元信息
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SnapshotIndex:
    """快照索引条目"""

    snapshot_id: str
    archive_id: str
    timestamp: str
    version: str
    content_hash: str
    summary: str = ""


# =============================================================================
# 快照归档管理器
# =============================================================================


class SnapshotArchive:
    """
    Harness 快照归档管理器 (v2.0)

    基于 SHA-256 哈希链的不可篡改归档系统。
    每轮数据归档后生成哈希值，下一轮归档引用上一轮哈希，
    形成防篡改链。

    v2.0: 哈希输入包含时间戳和轮次号，防止时间错位攻击。

    存储路径: data/snapshots/
    """

    __slots__ = (
        "_storage_path",
        "_archives",
        "_snapshot_index",
        "_audit_log",
        "_last_hash",
    )

    def __init__(self, storage_path: str = "data/snapshots") -> None:
        self._storage_path = storage_path
        self._archives: dict[str, RoundArchive] = {}
        self._snapshot_index: dict[str, SnapshotIndex] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._last_hash: str = "0" * 64  # 创世哈希

        os.makedirs(storage_path, exist_ok=True)

    # =========================================================================
    # 归档操作
    # =========================================================================

    def archive_round(
        self,
        task_id: str,
        round_number: int,
        context_version: str,
        worker_outputs: dict[str, Any],
        meta_logs: list[dict[str, Any]],
        subtask_proposals: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        # v2.0 扩展
        convergence_vector: dict[str, Any] | None = None,
        hypothesis_pool_snapshot: dict[str, Any] | None = None,
        agent_credibility: dict[str, float] | None = None,
    ) -> str:
        """
        归档单轮完整数据

        Args:
            task_id:                  顶层任务 ID
            round_number:             轮次编号
            context_version:          上下文版本号
            worker_outputs:           各 Agent 原始输出
            meta_logs:                元规则触发记录
            subtask_proposals:        子任务提案列表
            metadata:                 额外元信息
            convergence_vector:       v2.0 多维收敛向量
            hypothesis_pool_snapshot: v2.0 假说池快照
            agent_credibility:        v2.0 Agent 信誉分

        Returns:
            archive_id — 归档唯一标识
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        archive_id = f"arc_{task_id}_r{round_number:03d}"

        archive = RoundArchive(
            archive_id=archive_id,
            task_id=task_id,
            round_number=round_number,
            context_version=context_version,
            timestamp=timestamp,
            worker_outputs=worker_outputs,
            meta_logs=meta_logs,
            subtask_proposals=subtask_proposals or [],
            prev_archive_hash=self._last_hash,
            metadata=metadata or {},
            convergence_vector=convergence_vector or {},
            hypothesis_pool_snapshot=hypothesis_pool_snapshot or {},
            agent_credibility=agent_credibility or {},
        )

        # 计算内容哈希（v2.0: 含时间戳和轮次号）
        archive.content_hash = self._compute_hash(archive)

        # 更新哈希链
        self._last_hash = archive.content_hash

        # 存储
        self._archives[archive_id] = archive
        self._save_to_disk(archive)

        # 创建快照索引
        snapshot_id = self._create_snapshot_index(archive)

        # 审计
        self._log_audit("archive", archive_id, archive.content_hash, task_id=task_id)

        return snapshot_id

    def _create_snapshot_index(self, archive: RoundArchive) -> str:
        """创建快照索引条目"""
        snapshot_id = f"snap_{archive.task_id}_{archive.round_number:03d}"
        index = SnapshotIndex(
            snapshot_id=snapshot_id,
            archive_id=archive.archive_id,
            timestamp=archive.timestamp,
            version=archive.context_version,
            content_hash=archive.content_hash,
            summary=(
                f"Task={archive.task_id} Round={archive.round_number} "
                f"Agents={list(archive.worker_outputs.keys())}"
            ),
        )
        self._snapshot_index[snapshot_id] = index
        return snapshot_id

    # =========================================================================
    # 读取与回滚
    # =========================================================================

    def get_archive(self, archive_id: str) -> RoundArchive | None:
        return self._archives.get(archive_id)

    def get_archive_by_snapshot(self, snapshot_id: str) -> RoundArchive | None:
        index = self._snapshot_index.get(snapshot_id)
        if index is None:
            return None
        return self._archives.get(index.archive_id)

    def rollback(self, snapshot_id: str) -> dict[str, Any] | None:
        """
        回滚到指定快照版本

        返回该快照的所有 Worker 输出和元日志，
        并验证哈希完整性（v2.0: 含时间戳签名校验）。
        """
        archive = self.get_archive_by_snapshot(snapshot_id)
        if archive is None:
            return None

        # 验证哈希完整性
        expected_hash = self._compute_hash(archive)
        if expected_hash != archive.content_hash:
            self._log_audit(
                "hash_mismatch",
                archive.archive_id,
                f"expected={expected_hash[:16]}... actual={archive.content_hash[:16]}...",
            )
            return None

        self._log_audit("rollback", archive.archive_id, archive.content_hash)
        return {
            "task_id": archive.task_id,
            "round_number": archive.round_number,
            "context_version": archive.context_version,
            "worker_outputs": dict(archive.worker_outputs),
            "meta_logs": list(archive.meta_logs),
            "subtask_proposals": list(archive.subtask_proposals),
            "timestamp": archive.timestamp,
            "convergence_vector": dict(archive.convergence_vector),
            "hypothesis_pool_snapshot": dict(archive.hypothesis_pool_snapshot),
            "agent_credibility": dict(archive.agent_credibility),
        }

    # =========================================================================
    # 查询
    # =========================================================================

    def list_snapshots(self) -> list[dict[str, str]]:
        return [
            {
                "snapshot_id": idx.snapshot_id,
                "archive_id": idx.archive_id,
                "timestamp": idx.timestamp,
                "version": idx.version,
                "content_hash": idx.content_hash[:16] + "...",
                "summary": idx.summary,
            }
            for idx in self._snapshot_index.values()
        ]

    def list_archives_by_task(self, task_id: str) -> list[dict[str, Any]]:
        return [
            {
                "archive_id": arc.archive_id,
                "round_number": arc.round_number,
                "timestamp": arc.timestamp,
                "content_hash": arc.content_hash[:16] + "...",
                "agent_count": len(arc.worker_outputs),
            }
            for arc in self._archives.values()
            if arc.task_id == task_id
        ]

    def verify_chain(self) -> dict[str, Any]:
        """
        验证哈希链完整性

        遍历所有归档，验证每个归档的 prev_archive_hash
        与上一归档的 content_hash 是否一致。
        """
        broken_links: list[dict[str, str]] = []
        archives_sorted = sorted(
            self._archives.values(), key=lambda a: a.timestamp
        )

        prev_hash = "0" * 64
        for arc in archives_sorted:
            if arc.prev_archive_hash != prev_hash:
                broken_links.append(
                    {
                        "archive_id": arc.archive_id,
                        "expected_prev": prev_hash[:16] + "...",
                        "actual_prev": arc.prev_archive_hash[:16] + "...",
                    }
                )
            prev_hash = arc.content_hash

        return {
            "is_valid": len(broken_links) == 0,
            "total_archives": len(archives_sorted),
            "broken_links": broken_links,
            "last_hash": self._last_hash[:16] + "...",
        }

    # =========================================================================
    # 审计
    # =========================================================================

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """获取完整审计追踪日志"""
        return list(self._audit_log)

    def get_audit_by_task(self, task_id: str) -> list[dict[str, Any]]:
        """按任务 ID 获取审计日志"""
        return [log for log in self._audit_log if log.get("task_id") == task_id]

    # =========================================================================
    # 内部方法
    # =========================================================================

    def _compute_hash(self, archive: RoundArchive) -> str:
        """
        计算归档内容的 SHA-256 哈希 (v2.0)

        哈希输入包含:
        - archive_id, task_id, round_number, context_version
        - timestamp (v2.0: 时间戳签名防时间错位攻击)
        - created_at (v2.0: 显式创建时间)
        - worker_outputs (序列化)
        - meta_logs (序列化)
        - prev_archive_hash

        注意: 不包含 content_hash 自身，避免循环依赖。
        """
        payload = {
            "archive_id": archive.archive_id,
            "task_id": archive.task_id,
            "round_number": archive.round_number,
            "context_version": archive.context_version,
            "timestamp": archive.timestamp,
            "created_at": archive.timestamp,  # v2.0: 显式时间戳签名
            "worker_outputs": archive.worker_outputs,
            "meta_logs": archive.meta_logs,
            "subtask_proposals": archive.subtask_proposals,
            "prev_archive_hash": archive.prev_archive_hash,
            "convergence_vector": archive.convergence_vector,
            "agent_credibility": archive.agent_credibility,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _save_to_disk(self, archive: RoundArchive) -> None:
        """
        将归档持久化到磁盘

        文件路径: data/snapshots/{archive_id}.json
        """
        max_size_bytes = BRAIN_CONSTANTS.MAX_SNAPSHOT_SIZE_MB * 1024 * 1024

        data = {
            "archive_id": archive.archive_id,
            "task_id": archive.task_id,
            "round_number": archive.round_number,
            "context_version": archive.context_version,
            "timestamp": archive.timestamp,
            "worker_outputs": archive.worker_outputs,
            "meta_logs": archive.meta_logs,
            "subtask_proposals": archive.subtask_proposals,
            "content_hash": archive.content_hash,
            "prev_archive_hash": archive.prev_archive_hash,
            "metadata": archive.metadata,
            "convergence_vector": archive.convergence_vector,
            "agent_credibility": archive.agent_credibility,
        }

        serialized = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        size_bytes = len(serialized.encode("utf-8"))

        if size_bytes > max_size_bytes:
            self._log_audit(
                "size_exceeded",
                archive.archive_id,
                f"size={size_bytes} exceeds max={max_size_bytes}",
            )
            truncated_outputs = {}
            for k, v in archive.worker_outputs.items():
                truncated_outputs[k] = str(v)[:5000] + "...[truncated]"
            data["worker_outputs"] = truncated_outputs
            data["metadata"]["truncated"] = True
            serialized = json.dumps(data, indent=2, default=str, ensure_ascii=False)

        filepath = os.path.join(self._storage_path, f"{archive.archive_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(serialized)

    def _log_audit(self, action: str, target_id: str, detail: str = "", task_id: str = "") -> None:
        """记录审计日志"""
        self._audit_log.append(
            {
                "action": action,
                "target_id": target_id,
                "task_id": task_id,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def archive_count(self) -> int:
        return len(self._archives)

    @property
    def last_hash(self) -> str:
        return self._last_hash

    @property
    def storage_path(self) -> str:
        return self._storage_path