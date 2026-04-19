import sqlite3

import pytest

from scripts.init_sqlite import DEDUPE_SCHEMA
from src.webhook.dedupe_ledger import claim_event, is_claimed


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "dedupe.db"
    with sqlite3.connect(p) as conn:
        conn.executescript(DEDUPE_SCHEMA)
    return str(p)


def test_first_claim_succeeds(db_path):
    ok = claim_event(
        db_path,
        event_id="E1",
        team_id="T1",
        channel_id="C1",
        claimed_by="worker-A",
    )
    assert ok is True
    assert is_claimed(db_path, "E1")


def test_duplicate_claim_blocked(db_path):
    claim_event(
        db_path, event_id="E1", team_id="T1", channel_id="C1", claimed_by="A"
    )
    ok = claim_event(
        db_path, event_id="E1", team_id="T1", channel_id="C1", claimed_by="B"
    )
    assert ok is False


def test_distinct_events_both_claim(db_path):
    assert claim_event(db_path, event_id="E1", team_id=None, channel_id=None, claimed_by="A")
    assert claim_event(db_path, event_id="E2", team_id=None, channel_id=None, claimed_by="A")
