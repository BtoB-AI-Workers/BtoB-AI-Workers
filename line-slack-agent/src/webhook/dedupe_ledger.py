"""event_id主キーの重複排除台帳。

ack前の受信層で呼び出され、Slackの再送（X-Slack-Retry-Num）や
同一イベント重複発火を原子的にブロックする。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


@contextmanager
def _connect(db_path: str, *, busy_timeout_ms: int = 5000):
    path = _expand(db_path)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit off
    try:
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        conn.close()


def claim_event(
    db_path: str,
    *,
    event_id: str,
    team_id: str | None,
    channel_id: str | None,
    claimed_by: str,
) -> bool:
    """event_idをclaimする。すでに存在すればFalse（重複）。

    Returns:
        True: このプロセスが初claim、続きの処理を進めて良い
        False: 既にclaim済み（重複）
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO dedupe_ledger "
                "(event_id, claimed_at, claimed_by, team_id, channel_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_id, now, claimed_by, team_id, channel_id),
            )
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception:
            conn.execute("ROLLBACK")
            raise


def is_claimed(db_path: str, event_id: str) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM dedupe_ledger WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None
