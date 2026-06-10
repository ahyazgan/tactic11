"""app.scheduler.daemon — zamanlama çözümü + due mantığı + tick testleri."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import pytest

from app.db import models
from app.scheduler.daemon import (
    DEFAULT_SCHEDULE,
    ScheduleEntry,
    is_due,
    last_started_today,
    parse_schedule,
    tick,
)

NOW = datetime(2026, 6, 10, 7, 0, 0)   # yerel 07:00


# ── parse_schedule ──────────────────────────────────────────────────────────

def test_parse_schedule_empty_returns_default():
    assert parse_schedule(None) == DEFAULT_SCHEDULE
    assert parse_schedule("") == DEFAULT_SCHEDULE


def test_parse_schedule_json():
    raw = '[{"job":"reconcile_predictions","at":"05:15","kwargs":{"sport":"football"}}]'
    entries = parse_schedule(raw)
    assert entries == [ScheduleEntry("reconcile_predictions", "05:15", {"sport": "football"})]


@pytest.mark.parametrize("raw", [
    "not-json",
    '[{"at":"05:15"}]',                      # job eksik
    '[{"job":"x","at":"25:00"}]',            # saat aralık dışı
    '[{"job":"x","at":"0500"}]',             # format hatalı
])
def test_parse_schedule_invalid_raises(raw):
    with pytest.raises(ValueError):
        parse_schedule(raw)


# ── is_due ──────────────────────────────────────────────────────────────────

def test_not_due_before_scheduled_time():
    e = ScheduleEntry("j", "08:00")
    assert is_due(e, NOW, None) is False


def test_due_after_time_when_never_ran():
    e = ScheduleEntry("j", "06:30")
    assert is_due(e, NOW, None) is True


def test_not_due_when_already_ran_after_schedule():
    e = ScheduleEntry("j", "06:30")
    assert is_due(e, NOW, last_started=NOW.replace(hour=6, minute=31)) is False


def test_due_when_last_run_was_before_today_schedule():
    e = ScheduleEntry("j", "06:30")
    yesterday = NOW - timedelta(days=1)
    assert is_due(e, NOW, last_started=yesterday) is True


# ── tick + DB çift-koşu koruması ────────────────────────────────────────────

def _job_run(name: str, started_local: datetime) -> models.JobRun:
    # Kolon UTC tutar — yerel naive'i UTC'ye çevirip naive yaz (SQLite davranışı).
    started_utc = started_local.astimezone().astimezone(UTC).replace(tzinfo=None)
    return models.JobRun(
        job_name=name, args="{}", started_at=started_utc,
        status="success", attempts=1,
    )


def test_tick_runs_due_jobs_with_kwargs(session):
    calls: list[tuple[str, dict]] = []
    sched = [
        ScheduleEntry("alpha", "06:30", {"limit": 5}),
        ScheduleEntry("beta", "09:00"),              # henüz vakti gelmedi
    ]
    ran = tick(
        sched, now=NOW,
        runner=lambda name, **kw: calls.append((name, kw)),
        session_factory=lambda: nullcontext(session),
    )
    assert ran == ["alpha"]
    assert calls == [("alpha", {"limit": 5})]


def test_tick_skips_job_already_ran_today(session):
    session.add(_job_run("alpha", NOW.replace(hour=6, minute=35)))
    session.flush()
    calls: list[str] = []
    ran = tick(
        [ScheduleEntry("alpha", "06:30")], now=NOW,
        runner=lambda name, **kw: calls.append(name),
        session_factory=lambda: nullcontext(session),
    )
    assert ran == []
    assert calls == []


def test_tick_reruns_when_yesterdays_run_only(session):
    session.add(_job_run("alpha", NOW - timedelta(days=1)))
    session.flush()
    ran = tick(
        [ScheduleEntry("alpha", "06:30")], now=NOW,
        runner=lambda name, **kw: None,
        session_factory=lambda: nullcontext(session),
    )
    assert ran == ["alpha"]


def test_tick_one_failing_job_does_not_block_others(session):
    def runner(name: str, **kw):
        if name == "bad":
            raise KeyError("job kayıtlı değil")
    ran = tick(
        [ScheduleEntry("bad", "06:00"), ScheduleEntry("good", "06:30")],
        now=NOW, runner=runner,
        session_factory=lambda: nullcontext(session),
    )
    assert ran == ["good"]


def test_last_started_today_ignores_other_jobs_and_days(session):
    session.add_all([
        _job_run("alpha", NOW.replace(hour=3, minute=0)),
        _job_run("alpha", NOW - timedelta(days=1)),
        _job_run("beta", NOW.replace(hour=5, minute=0)),
    ])
    session.flush()
    last = last_started_today(session, "alpha", NOW)
    assert last is not None
    assert (last.hour, last.minute) == (3, 0)
