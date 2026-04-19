import hashlib
import hmac

from src.webhook.verify import (
    TIMESTAMP_TOLERANCE_SEC,
    verify_allowlist,
    verify_signature,
)


SECRET = "test_secret"


def _sign(ts: str, body: str) -> str:
    base = f"v0:{ts}:{body}".encode()
    return "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()


def test_valid_signature():
    ts = "1700000000"
    body = '{"event":"test"}'
    sig = _sign(ts, body)
    r = verify_signature(SECRET, ts, body, sig, now_unix=float(ts))
    assert r.ok


def test_signature_mismatch():
    ts = "1700000000"
    body = '{"event":"test"}'
    bad = "v0=ffff"
    r = verify_signature(SECRET, ts, body, bad, now_unix=float(ts))
    assert not r.ok
    assert r.reason == "signature_mismatch"


def test_timestamp_replay_rejected():
    ts = "1700000000"
    body = ""
    sig = _sign(ts, body)
    # ±5分を超える差分
    r = verify_signature(
        SECRET, ts, body, sig, now_unix=float(ts) + TIMESTAMP_TOLERANCE_SEC + 1
    )
    assert not r.ok
    assert r.reason == "timestamp_out_of_range"


def test_invalid_timestamp_format():
    r = verify_signature(SECRET, "not_a_number", "", "v0=x")
    assert not r.ok
    assert r.reason == "invalid_timestamp"


ALLOWLIST = {
    "team_id_allowlist": ["T1"],
    "main_channel": {"id": "CMAIN"},
    "audit_channel": {"id": "CAUDIT"},
    "bots": {"claude_bot_user_id": "UCLAUDE"},
    "allowed_event_sources": [
        {"allowed_user_ids": ["UZAPIER"], "allowed_human_user_ids": ["UOP"]}
    ],
}


def test_allowlist_pass():
    r = verify_allowlist("T1", "CMAIN", "UZAPIER", ALLOWLIST)
    assert r.ok


def test_allowlist_wrong_team():
    r = verify_allowlist("T9", "CMAIN", "UZAPIER", ALLOWLIST)
    assert not r.ok


def test_allowlist_wrong_channel():
    r = verify_allowlist("T1", "COTHER", "UZAPIER", ALLOWLIST)
    assert not r.ok


def test_allowlist_self_event_ignored():
    r = verify_allowlist("T1", "CMAIN", "UCLAUDE", ALLOWLIST)
    assert not r.ok
    assert r.reason == "self_event_ignored"


def test_allowlist_operator_allowed():
    r = verify_allowlist("T1", "CMAIN", "UOP", ALLOWLIST)
    assert r.ok
