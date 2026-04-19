"""Layer4 killswitch: 5粒度×3点チェック。

粒度: global / channel / job / candidate / thread
参照タイミング: worker_start / after_claude / before_send

発動経路:
  1. audit channel の `:octagonal_sign:` リアクションで activate
  2. DMスラッシュコマンドで明示 activate/deactivate
  3. 関連 queue はworkerが処理時にis_halted()を見てcancelled化
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


Scope = Literal["global", "channel", "job", "candidate", "thread"]
VALID_SCOPES: tuple[Scope, ...] = ("global", "channel", "job", "candidate", "thread")
CheckPoint = Literal["worker_start", "after_claude", "before_send"]


@dataclass(frozen=True)
class HaltCheck:
    halted: bool
    scope: Scope | None = None
    scope_id: str | None = None
    reason: str | None = None
    activated_at: str | None = None


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(_expand(db_path), isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def activate(
    db_path: str,
    scope: Scope,
    scope_id: str,
    activated_by: str,
    reason: str | None = None,
) -> None:
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid_scope: {scope}")
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO killswitch "
            "(scope, scope_id, activated_at, activated_by, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (scope, scope_id, now, activated_by, reason),
        )


def deactivate(db_path: str, scope: Scope, scope_id: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM killswitch WHERE scope=? AND scope_id=?",
            (scope, scope_id),
        )


def check(
    db_path: str,
    *,
    channel_id: str | None,
    job_id: str | None,
    candidate_id: str | None,
    thread_ts: str | None,
    check_point: CheckPoint,  # トレース用、判定ロジックには影響しない
) -> HaltCheck:
    """3点チェックのうちどの呼び出しでも同じAPI。記録のため check_point を受け取る。"""
    # scope -> scope_id mapping（優先順は粒度の粗さ順）
    lookups: list[tuple[Scope, str]] = [("global", "*")]
    if channel_id:
        lookups.append(("channel", channel_id))
    if job_id:
        lookups.append(("job", job_id))
    if candidate_id:
        lookups.append(("candidate", candidate_id))
    if thread_ts:
        lookups.append(("thread", thread_ts))

    with _connect(db_path) as conn:
        for scope, sid in lookups:
            row = conn.execute(
                "SELECT activated_at, reason FROM killswitch "
                "WHERE scope=? AND scope_id=? LIMIT 1",
                (scope, sid),
            ).fetchone()
            if row is not None:
                return HaltCheck(
                    halted=True,
                    scope=scope,
                    scope_id=sid,
                    reason=row["reason"],
                    activated_at=row["activated_at"],
                )
    return HaltCheck(halted=False)
