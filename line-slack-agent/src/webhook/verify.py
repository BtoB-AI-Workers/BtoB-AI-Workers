"""Slack署名検証・timestamp replay防止・allowlist照合。

ack前の原子的永続化の直前で実行される、受信層の入り口ガード。
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Mapping


TIMESTAMP_TOLERANCE_SEC = 300  # ±5分


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str = ""


def verify_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
    now_unix: float | None = None,
) -> VerifyResult:
    """Slack署名 + timestamp replay防止。"""
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return VerifyResult(False, "invalid_timestamp")

    now = now_unix if now_unix is not None else time.time()
    if abs(now - ts_int) > TIMESTAMP_TOLERANCE_SEC:
        return VerifyResult(False, "timestamp_out_of_range")

    basestring = f"v0:{timestamp}:{body}".encode("utf-8")
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), basestring, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return VerifyResult(False, "signature_mismatch")

    return VerifyResult(True)


def verify_allowlist(
    team_id: str,
    channel_id: str,
    user_id: str,
    allowlist: Mapping,
) -> VerifyResult:
    """team/channel/user のallowlist照合。

    allowlist schema: config/allowlist.yaml 参照。
    """
    allowed_teams = allowlist.get("team_id_allowlist") or []
    if allowed_teams and team_id not in allowed_teams:
        return VerifyResult(False, f"team_not_allowed:{team_id}")

    main = allowlist.get("main_channel", {})
    audit = allowlist.get("audit_channel", {})
    allowed_channels = {main.get("id"), audit.get("id")}
    allowed_channels.discard(None)
    if channel_id not in allowed_channels:
        return VerifyResult(False, f"channel_not_allowed:{channel_id}")

    # event source user: Zapier webhook bot or registered human operator or Claude bot
    sources = allowlist.get("allowed_event_sources") or []
    allowed_users = set()
    for src in sources:
        allowed_users.update(src.get("allowed_user_ids") or [])
        allowed_users.update(src.get("allowed_human_user_ids") or [])

    claude_bot = (allowlist.get("bots") or {}).get("claude_bot_user_id")
    if user_id == claude_bot:
        return VerifyResult(False, "self_event_ignored")

    if allowed_users and user_id not in allowed_users:
        return VerifyResult(False, f"user_not_allowed:{user_id}")

    return VerifyResult(True)
