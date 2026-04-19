"""SQLite初期化: queue.db / dedupe_ledger.db

ack前の原子的永続化のためにPhase 1から併用する。Sheetsは業務DB・監査用途のみ。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    source_channel TEXT NOT NULL,
    source_user TEXT NOT NULL,
    event_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE REFERENCES inbox(event_id),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    lease_owner TEXT,
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT UNIQUE,
    sent_marker_at TEXT,
    last_error TEXT,
    enqueued_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_lease_until ON queue(lease_until);

CREATE TABLE IF NOT EXISTS killswitch (
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    activated_at TEXT NOT NULL,
    activated_by TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (scope, scope_id)
);
"""


DEDUPE_SCHEMA = """
CREATE TABLE IF NOT EXISTS dedupe_ledger (
    event_id TEXT PRIMARY KEY,
    claimed_at TEXT NOT NULL,
    claimed_by TEXT NOT NULL,
    team_id TEXT,
    channel_id TEXT
);
"""


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _expand(path_str: str) -> Path:
    return Path(os.path.expanduser(path_str))


def init_databases(queue_db_path: str, dedupe_db_path: str) -> None:
    queue_path = _expand(queue_db_path)
    dedupe_path = _expand(dedupe_db_path)

    _ensure_dir(queue_path)
    _ensure_dir(dedupe_path)

    with sqlite3.connect(queue_path) as conn:
        conn.executescript(QUEUE_SCHEMA)
    with sqlite3.connect(dedupe_path) as conn:
        conn.executescript(DEDUPE_SCHEMA)

    print(f"[ok] queue.db initialized at {queue_path}")
    print(f"[ok] dedupe_ledger.db initialized at {dedupe_path}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    queue_db = os.environ.get("QUEUE_DB_PATH", "~/.local/share/line-slack-agent/queue.db")
    dedupe_db = os.environ.get(
        "DEDUPE_LEDGER_PATH", "~/.local/share/line-slack-agent/dedupe_ledger.db"
    )
    init_databases(queue_db, dedupe_db)
