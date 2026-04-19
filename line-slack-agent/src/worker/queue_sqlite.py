"""SQLiteベースのキュー。CAS相当のlease取得・期限切れrequeue・idempotency再確認。

ack前の受信層で `enqueue` され、ワーカーが `lease_next` で取り出す。
送信直前に `confirm_idempotency` を呼び、送信成功後に `mark_sent` する。
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


@contextmanager
def _connect(db_path: str, *, busy_timeout_ms: int = 5000) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_expand(db_path), isolation_level=None)
    try:
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue(
    db_path: str,
    *,
    event_id: str,
    raw_payload: str,
    source_channel: str,
    source_user: str,
    event_type: str,
    job_type: str,
) -> int:
    """inbox insert + queue insert を単一トランザクションで実行。

    Returns:
        queue_id
    Raises:
        sqlite3.IntegrityError: event_id または idempotency_key 重複
    """
    now = _now_iso()
    idempotency_key = f"{job_type}:{event_id}"
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO inbox "
                "(event_id, received_at, raw_payload, source_channel, source_user, event_type) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, now, raw_payload, source_channel, source_user, event_type),
            )
            cur = conn.execute(
                "INSERT INTO queue "
                "(event_id, job_type, status, idempotency_key, enqueued_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?, ?)",
                (event_id, job_type, idempotency_key, now, now),
            )
            conn.execute("COMMIT")
            return int(cur.lastrowid)
        except Exception:
            conn.execute("ROLLBACK")
            raise


def lease_next(
    db_path: str,
    *,
    worker_id: str | None = None,
    lease_duration_sec: int = 180,
) -> dict | None:
    """pending ジョブを1件 lease する。期限切れ leased も requeue して取り直せる。

    CAS相当: `UPDATE WHERE status='pending' RETURNING queue_id` 相当を
    SQLiteの `RETURNING` 節（3.35+）で実装。
    """
    owner = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    lease_until = (now + timedelta(seconds=lease_duration_sec)).isoformat()
    now_iso = now.isoformat()

    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # 期限切れ leased を pending に戻す
            conn.execute(
                "UPDATE queue "
                "SET status='pending', lease_owner=NULL, lease_until=NULL, "
                "    attempts=attempts+1, updated_at=? "
                "WHERE status='leased' AND lease_until < ?",
                (now_iso, now_iso),
            )

            # 最古の pending を 1件 lease
            row = conn.execute(
                "SELECT queue_id, event_id, job_type, attempts, idempotency_key "
                "FROM queue WHERE status='pending' "
                "ORDER BY enqueued_at ASC LIMIT 1"
            ).fetchone()

            if row is None:
                conn.execute("COMMIT")
                return None

            conn.execute(
                "UPDATE queue "
                "SET status='leased', lease_owner=?, lease_until=?, updated_at=? "
                "WHERE queue_id=? AND status='pending'",
                (owner, lease_until, now_iso, row["queue_id"]),
            )
            conn.execute("COMMIT")
            return dict(row) | {"lease_owner": owner, "lease_until": lease_until}
        except Exception:
            conn.execute("ROLLBACK")
            raise


def get_inbox(db_path: str, event_id: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM inbox WHERE event_id=?", (event_id,)
        ).fetchone()
        return dict(row) if row else None


def confirm_idempotency(db_path: str, queue_id: int, idempotency_key: str) -> bool:
    """送信直前の再確認。既に sent_marker がついていれば False。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT sent_marker_at, idempotency_key FROM queue WHERE queue_id=?",
            (queue_id,),
        ).fetchone()
        if row is None:
            return False
        if row["sent_marker_at"] is not None:
            return False
        if row["idempotency_key"] != idempotency_key:
            return False
        return True


def mark_sent(db_path: str, queue_id: int) -> None:
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE queue SET status='done', sent_marker_at=?, updated_at=? WHERE queue_id=?",
            (now, now, queue_id),
        )


def mark_failed(db_path: str, queue_id: int, error: str) -> None:
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE queue SET status='failed', last_error=?, updated_at=? WHERE queue_id=?",
            (error, now, queue_id),
        )


def mark_cancelled(db_path: str, queue_id: int, reason: str) -> None:
    now = _now_iso()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE queue SET status='cancelled', last_error=?, updated_at=? WHERE queue_id=?",
            (reason, now, queue_id),
        )
