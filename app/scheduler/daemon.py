"""Scheduler daemon — kayıtlı job'ları günlük saatlerde koşturur (stdlib).

APScheduler/Celery bağımlılığı YOK: dakikalık tick döngüsü + job başına
"her gün HH:MM" zamanlaması. Koşular `runner.run_job` üzerinden gider, yani
her çalıştırma `job_runs` tablosuna yazılır — bu kayıt aynı zamanda restart
sonrası çift-koşu korumasıdır (bugün planlanan saatten SONRA başlamış bir
koşu varsa entry o gün tekrar koşmaz).

Zamanlama kaynağı: `SCHEDULER_SCHEDULE` env değişkeni (JSON) ya da
DEFAULT_SCHEDULE. Saatler makinenin YEREL saatine göredir. Örnek:

    SCHEDULER_SCHEDULE=[{"job":"appearance_backfill","at":"03:30","kwargs":{"limit":40}},
                        {"job":"daily_decision_brief","at":"06:30"}]

Çalıştırma: `python scripts/scheduler_daemon.py` (Ctrl+C ile durur) ya da
cron/Görev Zamanlayıcı altında `--once` ile dakikalık tetikleme.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db import models
from app.db.session import SessionLocal
from app.scheduler.runner import run_job

log = get_logger(__name__)

ENV_VAR = "SCHEDULER_SCHEDULE"


@dataclass(frozen=True)
class ScheduleEntry:
    job: str
    at: str                                  # "HH:MM" — yerel saat
    kwargs: dict[str, Any] = field(default_factory=dict)


# Pilot varsayılanı: gece veri çek, sabah brief hazırla.
DEFAULT_SCHEDULE: list[ScheduleEntry] = [
    ScheduleEntry("appearance_backfill", "03:30", {"limit": 40}),
    ScheduleEntry("reconcile_predictions", "04:00"),
    ScheduleEntry("daily_decision_brief", "06:30"),
]


def parse_schedule(raw: str | None) -> list[ScheduleEntry]:
    """SCHEDULER_SCHEDULE JSON'unu çöz; boş/yok → DEFAULT_SCHEDULE."""
    if not raw or not raw.strip():
        return list(DEFAULT_SCHEDULE)
    try:
        data = json.loads(raw)
        entries = [
            ScheduleEntry(
                job=str(item["job"]),
                at=str(item["at"]),
                kwargs=dict(item.get("kwargs") or {}),
            )
            for item in data
        ]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"{ENV_VAR} geçersiz: {e}") from e
    for ent in entries:
        _parse_hhmm(ent.at)  # erken doğrulama — hatalı saat daemon'u başlatmasın
    return entries


def _parse_hhmm(at: str) -> tuple[int, int]:
    try:
        hh, mm = at.split(":")
        h, m = int(hh), int(mm)
    except ValueError as e:
        raise ValueError(f"saat 'HH:MM' olmalı: {at!r}") from e
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"saat aralık dışı: {at!r}")
    return h, m


def scheduled_dt_for(entry: ScheduleEntry, now: datetime) -> datetime:
    """Entry'nin bugünkü planlanan zamanı (now ile aynı tz-yapıda)."""
    h, m = _parse_hhmm(entry.at)
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def is_due(entry: ScheduleEntry, now: datetime, last_started: datetime | None) -> bool:
    """Şimdi koşmalı mı? now >= bugünkü plan VE bugünkü plandan sonra koşulmamış."""
    sched = scheduled_dt_for(entry, now)
    if now < sched:
        return False
    return last_started is None or last_started < sched


def _to_local_naive(dt: datetime) -> datetime:
    """DB'den gelen started_at'i yerel naive'e çevir.

    SQLite tz-aware kolonu naive-UTC döndürür; Postgres aware döndürür.
    İkisini de yerel duvar-saatine indirger (zamanlama yerel HH:MM olduğundan).
    """
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone().replace(tzinfo=None)


def last_started_today(session: Session, job_name: str, now: datetime) -> datetime | None:
    """Bu job'ın bugün (yerel) başlamış son koşusu — status fark etmez.

    'running' da sayılır: uzun süren bir koşu sürerken ikinci kez tetiklenmez.
    """
    # Yerel gün başlangıcını UTC'ye çevirip DB'de karşılaştır (kolon UTC tutar).
    local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone().astimezone(UTC).replace(tzinfo=None)
    rows = session.execute(
        select(models.JobRun.started_at)
        .where(
            models.JobRun.job_name == job_name,
            models.JobRun.started_at >= utc_midnight,
        )
        .order_by(models.JobRun.started_at.desc())
        .limit(1)
    ).scalars().first()
    return _to_local_naive(rows) if rows is not None else None


def tick(
    schedule: list[ScheduleEntry],
    *,
    now: datetime | None = None,
    runner: Callable[..., Any] = run_job,
    session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
) -> list[str]:
    """Tek tarama: vakti gelmiş job'ları koştur, koşanların adını döndür.

    runner/session_factory parametreleri test enjeksiyonu içindir. Bir job'ın
    patlaması diğerlerini engellemez (runner zaten handler hatalarını yutar;
    kayıt-dışı job adı gibi kurulum hataları burada loglanıp geçilir).
    """
    now = now or datetime.now()
    ran: list[str] = []
    for entry in schedule:
        with session_factory() as session:
            last = last_started_today(session, entry.job, now)
        if not is_due(entry, now, last):
            continue
        log.info("scheduler: %s vakti geldi (at=%s) — koşturuluyor", entry.job, entry.at)
        try:
            runner(entry.job, **entry.kwargs)
            ran.append(entry.job)
        except Exception as e:  # noqa: BLE001 — bir job diğerlerini düşürmesin
            log.error("scheduler: %s koşturulamadı: %s: %s", entry.job, type(e).__name__, e)
    return ran


def run_daemon(
    *, interval_seconds: int = 30, once: bool = False,
    schedule: list[ScheduleEntry] | None = None,
) -> None:
    """Daemon döngüsü. once=True → tek tick (cron/Görev Zamanlayıcı modu)."""
    sched = schedule if schedule is not None else parse_schedule(os.environ.get(ENV_VAR))
    log.info(
        "scheduler daemon başladı: %d entry — %s",
        len(sched), ", ".join(f"{e.job}@{e.at}" for e in sched),
    )
    while True:
        tick(sched)
        if once:
            return
        time.sleep(interval_seconds)
