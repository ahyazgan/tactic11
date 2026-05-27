"""Job çalıştırıcı + retry + audit.

`run_job(name, **kwargs)` bir kayda bağlı işi çağırır. Akış:
1) `job_runs` tablosuna 'running' satırı yaz.
2) handler'ı çağır; başarılıysa break, exception'da `_sleep()` ile bekleyip
   tekrar dene; `max_attempts`'e kadar.
3) Sonuç + son hata + deneme sayısı ile satırı güncelle.

Bir job çağrısı = bir satır. Retry'lar attempt sayısına yansır, ayrı satır olmaz.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.db import models
from app.db.session import SessionLocal
from app.scheduler.registry import get as get_spec

log = get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 2.0


def _sleep(seconds: float) -> None:
    """Test'lerde monkeypatch'lenebilen ince sarmalayıcı."""
    time.sleep(seconds)


def _backoff(attempt: int) -> float:
    return DEFAULT_BACKOFF_SECONDS * (2 ** (attempt - 1))


def run_job(
    name: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    **kwargs: Any,
) -> models.JobRun:
    spec = get_spec(name)
    args_json = json.dumps(kwargs, sort_keys=True, default=str)

    with SessionLocal() as session:
        row = models.JobRun(
            job_name=name,
            args=args_json,
            started_at=datetime.now(timezone.utc),
            status="running",
            attempts=0,
        )
        session.add(row)
        session.commit()
        run_id = row.id

    last_error: str | None = None
    final_status = "failed"
    attempts_made = 0

    try:
        for attempt in range(1, max_attempts + 1):
            attempts_made = attempt
            log.info("job %s deneme %d/%d kwargs=%s", name, attempt, max_attempts, kwargs)
            try:
                spec.handler(**kwargs)
                final_status = "success"
                last_error = None
                break
            except Exception as e:  # noqa: BLE001 — job hataları yakalanır, audit'e yazılır
                last_error = f"{type(e).__name__}: {e}"
                log.warning("job %s deneme %d başarısız: %s", name, attempt, last_error)
                if attempt < max_attempts:
                    _sleep(_backoff(attempt))
    except BaseException as e:
        # KeyboardInterrupt / SystemExit vb — audit'i de işaretle, sonra reraise et.
        last_error = f"{type(e).__name__}: {e}"
        attempts_made = max(attempts_made, 1)
        _finalize_run(run_id, status="failed", attempts=attempts_made, error=last_error)
        raise

    return _finalize_run(run_id, status=final_status, attempts=attempts_made, error=last_error)


def _finalize_run(run_id: int, *, status: str, attempts: int, error: str | None) -> models.JobRun:
    with SessionLocal() as session:
        row = session.get(models.JobRun, run_id)
        if row is None:
            raise RuntimeError(f"job_run {run_id} kayboldu")
        row.status = status
        row.ended_at = datetime.now(timezone.utc)
        row.attempts = attempts
        row.error = error
        session.commit()
        session.refresh(row)
        return row
