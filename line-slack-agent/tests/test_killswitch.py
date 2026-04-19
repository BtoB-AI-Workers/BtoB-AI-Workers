import sqlite3

import pytest

from scripts.init_sqlite import QUEUE_SCHEMA
from src.guardrails.l4_killswitch import activate, check, deactivate


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "queue.db"
    with sqlite3.connect(p) as conn:
        conn.executescript(QUEUE_SCHEMA)
    return str(p)


def test_no_halt_by_default(db_path):
    r = check(
        db_path,
        channel_id="CMAIN",
        job_id="J1",
        candidate_id="U1",
        thread_ts="1.0",
        check_point="worker_start",
    )
    assert not r.halted


def test_global_halt_stops_everything(db_path):
    activate(db_path, "global", "*", "tester", reason="emergency")
    r = check(
        db_path,
        channel_id="CMAIN",
        job_id="J1",
        candidate_id="U1",
        thread_ts="1.0",
        check_point="before_send",
    )
    assert r.halted
    assert r.scope == "global"


def test_candidate_halt_specific(db_path):
    activate(db_path, "candidate", "U1", "tester")
    r_hit = check(
        db_path,
        channel_id="CMAIN",
        job_id="J1",
        candidate_id="U1",
        thread_ts=None,
        check_point="after_claude",
    )
    r_miss = check(
        db_path,
        channel_id="CMAIN",
        job_id="J1",
        candidate_id="U2",
        thread_ts=None,
        check_point="after_claude",
    )
    assert r_hit.halted
    assert not r_miss.halted


def test_deactivate(db_path):
    activate(db_path, "channel", "CMAIN", "tester")
    assert check(
        db_path,
        channel_id="CMAIN",
        job_id=None,
        candidate_id=None,
        thread_ts=None,
        check_point="worker_start",
    ).halted
    deactivate(db_path, "channel", "CMAIN")
    assert not check(
        db_path,
        channel_id="CMAIN",
        job_id=None,
        candidate_id=None,
        thread_ts=None,
        check_point="worker_start",
    ).halted


def test_invalid_scope_raises(db_path):
    with pytest.raises(ValueError):
        activate(db_path, "bogus", "x", "tester")  # type: ignore[arg-type]
