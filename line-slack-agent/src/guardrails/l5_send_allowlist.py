"""Layer5 送信先allowlist照合。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SendCheck:
    ok: bool
    reason: str = ""


def check_send_target(
    *,
    target_channel_id: str,
    allowlist: Mapping,
) -> SendCheck:
    targets = allowlist.get("allowed_send_targets") or []
    allowed_ids = set()
    for t in targets:
        ch = t.get("channel")
        if isinstance(ch, str):
            # allowlist.yaml の構造では `channel: main_channel` (エイリアス) or 直接ID
            alias_ch = allowlist.get(ch) or {}
            cid = alias_ch.get("id") if isinstance(alias_ch, dict) else ch
            if cid:
                allowed_ids.add(cid)
        elif isinstance(ch, dict):
            cid = ch.get("id")
            if cid:
                allowed_ids.add(cid)

    if target_channel_id not in allowed_ids:
        return SendCheck(False, f"send_target_not_allowed:{target_channel_id}")
    return SendCheck(True)
