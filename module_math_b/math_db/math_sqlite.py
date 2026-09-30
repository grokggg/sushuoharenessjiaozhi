"""
module_math_b.math_db.math_sqlite — 数学模块独立数据库

完全独立 SQLite 数据库，零共享主系统任何 IO 资源。
独立连接池、独立缓存、独立文件路径。

彻底杜绝：锁表、阻塞、资源抢占、内存交叉污染。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator


# =============================================================================
# 独立连接池
# =============================================================================

class MathConnectionPool:
    """
    数学模块专用连接池

    完全独立于主系统的任何数据库连接。
    线程安全，支持并发读写。
    """

    __slots__ = ("_db_path", "_pool", "_lock", "_max_connections", "_in_use")

    def __init__(self, db_path: str, max_connections: int = 4) -> None:
        self._db_path = db_path
        self._max_connections = max_connections
        self._pool: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._in_use: set[int] = set()

        # 预创建连接
        for _ in range(max_connections):
            conn = self._create_connection()
            self._pool.append(conn)

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取一个连接（上下文管理器，自动归还）"""
        conn = None
        conn_idx = -1
        with self._lock:
            for i, c in enumerate(self._pool):
                if i not in self._in_use:
                    self._in_use.add(i)
                    conn = c
                    conn_idx = i
                    break

        if conn is None:
            # 池满，创建临时连接
            conn = self._create_connection()
            conn_idx = -2  # 临时连接标记

        try:
            yield conn
        finally:
            if conn_idx >= 0:
                with self._lock:
                    self._in_use.discard(conn_idx)
            elif conn_idx == -2:
                conn.close()

    def close_all(self) -> None:
        """关闭所有连接"""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()
            self._in_use.clear()


# =============================================================================
# 独立数据库
# =============================================================================

class MathDatabase:
    """
    数学模块独立 SQLite 数据库

    完全独立存储：
      - 命题表
      - 推导步骤表
      - 反例表
      - 校验报告表
      - 快照元数据表
      - 会话日志表
    """

    DB_VERSION = 1

    __slots__ = ("_db_path", "_pool", "_closed")

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "module_math_b", "math_db", "data",
            )
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "math_module.db")

        self._db_path = db_path
        self._pool = MathConnectionPool(db_path, max_connections=4)
        self._closed = False

        self._init_schema()

    # =========================================================================
    # Schema 初始化
    # =========================================================================

    def _init_schema(self) -> None:
        with self._pool.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS math_propositions (
                    proposition_id   TEXT PRIMARY KEY,
                    statement        TEXT NOT NULL,
                    domain           TEXT NOT NULL DEFAULT 'number_theory',
                    difficulty       TEXT NOT NULL DEFAULT 'intermediate',
                    iteration_depth  INTEGER NOT NULL DEFAULT 0,
                    status           TEXT NOT NULL DEFAULT 'PENDING',
                    proven_by        TEXT DEFAULT '',
                    proof_chain_hash TEXT DEFAULT '',
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS math_derivation_steps (
                    step_id           TEXT PRIMARY KEY,
                    proposition_id    TEXT NOT NULL,
                    step_number       INTEGER NOT NULL,
                    premises          TEXT NOT NULL DEFAULT '[]',
                    conclusion        TEXT NOT NULL DEFAULT '',
                    derivation_rule   TEXT NOT NULL DEFAULT '',
                    justification     TEXT NOT NULL DEFAULT '',
                    has_gap           INTEGER NOT NULL DEFAULT 0,
                    gap_description   TEXT DEFAULT '',
                    has_hidden_assumption INTEGER NOT NULL DEFAULT 0,
                    hidden_assumption TEXT DEFAULT '',
                    is_circular       INTEGER NOT NULL DEFAULT 0,
                    circular_reference TEXT DEFAULT '',
                    validation_passed INTEGER NOT NULL DEFAULT 0,
                    validation_errors TEXT NOT NULL DEFAULT '[]',
                    source_agent      TEXT DEFAULT '',
                    created_at        TEXT NOT NULL,
                    FOREIGN KEY (proposition_id) REFERENCES math_propositions(proposition_id)
                );

                CREATE TABLE IF NOT EXISTS math_counter_examples (
                    example_id          TEXT PRIMARY KEY,
                    target_proposition_id TEXT NOT NULL,
                    value_representation TEXT NOT NULL DEFAULT '',
                    domain_check        TEXT DEFAULT '',
                    constraint_check    TEXT DEFAULT '',
                    is_valid            INTEGER NOT NULL DEFAULT 0,
                    invalid_reason      TEXT DEFAULT '',
                    is_reproducible     INTEGER NOT NULL DEFAULT 0,
                    verification_steps  TEXT NOT NULL DEFAULT '[]',
                    source_agent        TEXT DEFAULT '',
                    created_at          TEXT NOT NULL,
                    FOREIGN KEY (target_proposition_id) REFERENCES math_propositions(proposition_id)
                );

                CREATE TABLE IF NOT EXISTS math_validation_reports (
                    report_id         TEXT PRIMARY KEY,
                    proposition_id    TEXT NOT NULL,
                    round_number      INTEGER NOT NULL DEFAULT 0,
                    syntax_valid      INTEGER NOT NULL DEFAULT 1,
                    syntax_errors     TEXT NOT NULL DEFAULT '[]',
                    logical_gaps      TEXT NOT NULL DEFAULT '[]',
                    hidden_assumptions TEXT NOT NULL DEFAULT '[]',
                    circular_found    INTEGER NOT NULL DEFAULT 0,
                    overall_valid     INTEGER NOT NULL DEFAULT 0,
                    overall_score     REAL NOT NULL DEFAULT 0.0,
                    requires_iteration INTEGER NOT NULL DEFAULT 1,
                    iteration_hints   TEXT NOT NULL DEFAULT '[]',
                    created_at        TEXT NOT NULL,
                    FOREIGN KEY (proposition_id) REFERENCES math_propositions(proposition_id)
                );

                CREATE TABLE IF NOT EXISTS math_snapshots (
                    snapshot_id       TEXT PRIMARY KEY,
                    task_id           TEXT NOT NULL,
                    round_number      INTEGER NOT NULL,
                    timestamp         TEXT NOT NULL,
                    content_hash      TEXT NOT NULL DEFAULT '',
                    prev_snapshot_hash TEXT NOT NULL DEFAULT '',
                    extension_tag     TEXT NOT NULL DEFAULT 'MATH_B_EXT',
                    snapshot_data     TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS math_session_log (
                    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    event       TEXT NOT NULL,
                    detail      TEXT DEFAULT '',
                    created_at  TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_propositions_status ON math_propositions(status);
                CREATE INDEX IF NOT EXISTS idx_propositions_domain ON math_propositions(domain);
                CREATE INDEX IF NOT EXISTS idx_derivation_prop ON math_derivation_steps(proposition_id);
                CREATE INDEX IF NOT EXISTS idx_counter_prop ON math_counter_examples(target_proposition_id);
                CREATE INDEX IF NOT EXISTS idx_validation_prop ON math_validation_reports(proposition_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_task ON math_snapshots(task_id);
            """)
            conn.commit()

    # =========================================================================
    # 命题 CRUD
    # =========================================================================

    def insert_proposition(self, prop: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO math_propositions
                   (proposition_id, statement, domain, difficulty, iteration_depth,
                    status, proven_by, proof_chain_hash, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    prop["proposition_id"], prop.get("statement", ""),
                    prop.get("domain", "number_theory"), prop.get("difficulty", "intermediate"),
                    prop.get("iteration_depth", 0), prop.get("status", "PENDING"),
                    prop.get("proven_by", ""), prop.get("proof_chain_hash", ""),
                    prop.get("created_at", now), now,
                ),
            )
            conn.commit()

    def get_proposition(self, proposition_id: str) -> dict[str, Any] | None:
        with self._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM math_propositions WHERE proposition_id = ?",
                (proposition_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_proposition_status(
        self, proposition_id: str, status: str, proven_by: str = "", proof_hash: str = ""
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                """UPDATE math_propositions
                   SET status = ?, proven_by = ?, proof_chain_hash = ?, updated_at = ?
                   WHERE proposition_id = ?""",
                (status, proven_by, proof_hash, now, proposition_id),
            )
            conn.commit()

    def list_propositions_by_status(self, status: str) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM math_propositions WHERE status = ?", (status,)
            ).fetchall()
            return [dict(r) for r in rows]

    def list_all_propositions(self) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute("SELECT * FROM math_propositions").fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # 推导步骤 CRUD
    # =========================================================================

    def insert_derivation_step(self, step: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO math_derivation_steps
                   (step_id, proposition_id, step_number, premises, conclusion,
                    derivation_rule, justification, has_gap, gap_description,
                    has_hidden_assumption, hidden_assumption, is_circular,
                    circular_reference, validation_passed, validation_errors,
                    source_agent, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    step["step_id"], step["proposition_id"], step.get("step_number", 0),
                    _to_json(step.get("premises", [])), step.get("conclusion", ""),
                    step.get("derivation_rule", ""), step.get("justification", ""),
                    int(step.get("has_gap", False)), step.get("gap_description", ""),
                    int(step.get("has_hidden_assumption", False)), step.get("hidden_assumption", ""),
                    int(step.get("is_circular", False)), step.get("circular_reference", ""),
                    int(step.get("validation_passed", False)),
                    _to_json(step.get("validation_errors", [])),
                    step.get("source_agent", ""), now,
                ),
            )
            conn.commit()

    def get_derivation_steps(self, proposition_id: str) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM math_derivation_steps WHERE proposition_id = ? ORDER BY step_number",
                (proposition_id,),
            ).fetchall()
            return [_parse_derivation_step(dict(r)) for r in rows]

    def count_gaps(self, proposition_id: str) -> int:
        with self._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM math_derivation_steps WHERE proposition_id = ? AND has_gap = 1",
                (proposition_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    # =========================================================================
    # 反例 CRUD
    # =========================================================================

    def insert_counter_example(self, ce: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO math_counter_examples
                   (example_id, target_proposition_id, value_representation,
                    domain_check, constraint_check, is_valid, invalid_reason,
                    is_reproducible, verification_steps, source_agent, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ce["example_id"], ce["target_proposition_id"],
                    ce.get("value_representation", ""), ce.get("domain_check", ""),
                    ce.get("constraint_check", ""), int(ce.get("is_valid", False)),
                    ce.get("invalid_reason", ""), int(ce.get("is_reproducible", False)),
                    _to_json(ce.get("verification_steps", [])),
                    ce.get("source_agent", ""), now,
                ),
            )
            conn.commit()

    def get_valid_counter_examples(self, proposition_id: str) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM math_counter_examples WHERE target_proposition_id = ? AND is_valid = 1",
                (proposition_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # 校验报告 CRUD
    # =========================================================================

    def insert_validation_report(self, report: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO math_validation_reports
                   (report_id, proposition_id, round_number, syntax_valid,
                    syntax_errors, logical_gaps, hidden_assumptions,
                    circular_found, overall_valid, overall_score,
                    requires_iteration, iteration_hints, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report["report_id"], report["proposition_id"],
                    report.get("round_number", 0), int(report.get("syntax_valid", True)),
                    _to_json(report.get("syntax_errors", [])),
                    _to_json(report.get("logical_gaps", [])),
                    _to_json(report.get("hidden_assumptions", [])),
                    int(report.get("circular_found", False)),
                    int(report.get("overall_valid", False)),
                    report.get("overall_score", 0.0),
                    int(report.get("requires_iteration", True)),
                    _to_json(report.get("iteration_hints", [])),
                    now,
                ),
            )
            conn.commit()

    # =========================================================================
    # 快照 CRUD
    # =========================================================================

    def insert_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._pool.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO math_snapshots
                   (snapshot_id, task_id, round_number, timestamp, content_hash,
                    prev_snapshot_hash, extension_tag, snapshot_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot["snapshot_id"], snapshot["task_id"],
                    snapshot.get("round_number", 0), snapshot.get("timestamp", ""),
                    snapshot.get("content_hash", ""), snapshot.get("prev_snapshot_hash", ""),
                    "MATH_B_EXT", _to_json(snapshot.get("snapshot_data", {})),
                ),
            )
            conn.commit()

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._pool.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM math_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_snapshots_by_task(self, task_id: str) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM math_snapshots WHERE task_id = ? ORDER BY round_number",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # 会话日志
    # =========================================================================

    def log_event(self, session_id: str, event: str, detail: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._pool.get_connection() as conn:
            conn.execute(
                "INSERT INTO math_session_log (session_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
                (session_id, event, detail, now),
            )
            conn.commit()

    def get_session_logs(self, session_id: str) -> list[dict[str, Any]]:
        with self._pool.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM math_session_log WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # 生命周期
    # =========================================================================

    def close(self) -> None:
        if not self._closed:
            self._pool.close_all()
            self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def db_path(self) -> str:
        return self._db_path


# =============================================================================
# 辅助
# =============================================================================

import json

def _to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _parse_derivation_step(row: dict[str, Any]) -> dict[str, Any]:
    """解析数据库行中的 JSON 字段"""
    row["premises"] = _safe_json_parse(row.get("premises", "[]"), [])
    row["validation_errors"] = _safe_json_parse(row.get("validation_errors", "[]"), [])
    row["has_gap"] = bool(row.get("has_gap", 0))
    row["has_hidden_assumption"] = bool(row.get("has_hidden_assumption", 0))
    row["is_circular"] = bool(row.get("is_circular", 0))
    row["validation_passed"] = bool(row.get("validation_passed", 0))
    return row


def _safe_json_parse(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default