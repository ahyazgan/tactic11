from __future__ import annotations

from sqlalchemy import func, select

from app.db import models
from app.scheduler import runner as runner_module
from app.scheduler.registry import _REGISTRY, JobSpec, register


class _CtxSession:
    """SessionLocal yerine test fixture'ının açtığı session'ı geri verir."""

    def __init__(self, s):
        self.s = s

    def __enter__(self):
        return self.s

    def __exit__(self, *a):
        return False


def _patch_session(monkeypatch, session):
    monkeypatch.setattr(runner_module, "SessionLocal", lambda: _CtxSession(session))


def _register_once(name: str, handler) -> None:
    if name not in _REGISTRY:
        register(JobSpec(name=name, handler=handler))
    else:
        _REGISTRY[name] = JobSpec(name=name, handler=handler)


def test_run_job_success_records_one_run(session, monkeypatch):
    calls = []

    def handler(*, x: int):
        calls.append(x)

    _register_once("test_success", handler)
    _patch_session(monkeypatch, session)

    result = runner_module.run_job("test_success", x=42)
    assert result.status == "success"
    assert result.attempts == 1
    assert result.error is None
    assert calls == [42]

    n = session.scalar(select(func.count()).select_from(models.JobRun))
    assert n == 1


def test_run_job_retries_until_success(session, monkeypatch):
    counter = {"n": 0}

    def handler():
        counter["n"] += 1
        if counter["n"] < 3:
            raise RuntimeError("geçici hata")

    _register_once("test_retry", handler)
    _patch_session(monkeypatch, session)
    monkeypatch.setattr(runner_module, "_sleep", lambda s: None)

    result = runner_module.run_job("test_retry", max_attempts=5)
    assert result.status == "success"
    assert result.attempts == 3
    assert counter["n"] == 3


def test_run_job_marks_failed_after_exhausted(session, monkeypatch):
    def handler():
        raise ValueError("kalıcı hata")

    _register_once("test_fail", handler)
    _patch_session(monkeypatch, session)
    monkeypatch.setattr(runner_module, "_sleep", lambda s: None)

    result = runner_module.run_job("test_fail", max_attempts=2)
    assert result.status == "failed"
    assert result.attempts == 2
    assert "ValueError" in result.error
    assert "kalıcı hata" in result.error


def test_unknown_job_raises_keyerror(session, monkeypatch):
    _patch_session(monkeypatch, session)
    try:
        runner_module.run_job("yok_böyle_bir_iş")
    except KeyError as e:
        assert "yok_böyle_bir_iş" in str(e)
    else:
        raise AssertionError("KeyError beklendi")


def test_args_serialized_to_json_in_audit(session, monkeypatch):
    def handler(*, league_id: int, season: int):
        pass

    _register_once("test_args", handler)
    _patch_session(monkeypatch, session)

    runner_module.run_job("test_args", league_id=203, season=2024)
    row = session.execute(
        select(models.JobRun).where(models.JobRun.job_name == "test_args")
    ).scalar_one()
    assert '"league_id": 203' in row.args
    assert '"season": 2024' in row.args


def test_base_exception_still_writes_audit(session, monkeypatch):
    # KeyboardInterrupt / SystemExit gibi BaseException atılırsa JobRun satırı
    # 'running' kalmasın; exception reraise edilsin.
    import pytest as _pytest

    def handler():
        raise KeyboardInterrupt()

    _register_once("test_ki", handler)
    _patch_session(monkeypatch, session)

    with _pytest.raises(KeyboardInterrupt):
        runner_module.run_job("test_ki")

    row = session.execute(
        select(models.JobRun).where(models.JobRun.job_name == "test_ki")
    ).scalar_one()
    assert row.status == "failed"
    assert row.attempts == 1
    assert "KeyboardInterrupt" in row.error
    assert row.ended_at is not None
