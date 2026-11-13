"""/tracking kalibrasyon, video ve iş uçları — işçi stub ile uçtan uca."""
from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import tracking_jobs
from app.api.main import app
from app.db import models
from app.db.session import get_session

STUB = Path(__file__).parent / "fixtures" / "stub_track_video.py"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKING_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRACKING_WORKER_CMD", json.dumps([sys.executable, str(STUB)]))
    monkeypatch.delenv("TRACKING_WEIGHTS", raising=False)
    # Sahte işçi bellek istemez; testler makinenin o anki boş belleğine bağlı kalmasın.
    monkeypatch.setenv("TRACKING_MIN_COMMIT_MB", "0")
    return tmp_path


@pytest.fixture()
def client(session, env):
    session.info["tenant_id"] = "t-default"
    now = datetime.now(UTC)
    session.add(models.Tenant(id="t-default", slug="t-default", name="X", settings_json="{}", active=True, created_at=now))
    session.add(models.User(id="u1", tenant_id="t-default", email="a@b", password_hash="x", role="admin", active=True, created_at=now))
    session.commit()

    def _override():
        yield session
    app.dependency_overrides[get_session] = _override
    # Legacy X-API-Key yolu: settings api_auth_key boş → JWT gerekir; test için bypass
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: session.query(models.User).first()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


CALIB = {
    "image_size": [1300, 800],
    "points": [
        {"image": [100, 50], "pitch": [0, 0]}, {"image": [1150, 50], "pitch": [105, 0]},
        {"image": [1150, 730], "pitch": [105, 68]}, {"image": [100, 730], "pitch": [0, 68]},
    ],
    "meta": {"camera": "test"},
}


@pytest.fixture()
def summary_cache():
    tracking_jobs._cached_calib_summary.cache_clear()
    yield
    tracking_jobs._cached_calib_summary.cache_clear()


def test_calibration_summary_reuses_validation_but_rechecks_changed_content(monkeypatch, summary_cache):
    original = tracking_jobs._calculate_calib_summary
    calls = []

    def calculate(name, payload):
        calls.append(payload)
        return original(name, payload)

    monkeypatch.setattr(tracking_jobs, "_calculate_calib_summary", calculate)
    first = tracking_jobs._calib_summary("cached", CALIB)
    assert tracking_jobs._calib_summary("cached", dict(reversed(list(CALIB.items())))) == first
    assert len(calls) == 1
    changed = deepcopy(CALIB)
    changed["points"][0]["image"][0] = 101
    tracking_jobs._calib_summary("cached", changed)
    assert len(calls) == 2


def test_calibration_summary_result_cannot_poison_future_responses(summary_cache):
    first = tracking_jobs._calib_summary("safe", CALIB)
    first["meta"]["camera"] = "tampered"
    first["valid"] = False
    again = tracking_jobs._calib_summary("safe", CALIB)
    assert again["meta"] == {"camera": "test"}
    assert again["valid"] is True


def test_calibration_list_rechecks_replaced_file_and_removes_deleted_file(client, env, summary_cache):
    import os

    folder = env / "calibrations"
    folder.mkdir()
    path = folder / "same.json"
    invalid = deepcopy(CALIB)
    invalid["image_size"] = [-300, 800]
    path.write_text(json.dumps(invalid))
    stamp = path.stat()
    assert client.get("/tracking/calibrations").json()["calibrations"][0]["valid"] is False
    path.write_text(json.dumps(CALIB))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert path.stat().st_size == stamp.st_size
    assert client.get("/tracking/calibrations").json()["calibrations"][0]["valid"] is True
    path.unlink()
    assert client.get("/tracking/calibrations").json() == {"calibrations": [], "total": 0}


def test_calibration_blas_limits_restore_after_validation_failure(monkeypatch, summary_cache):
    from contextlib import contextmanager

    events = []

    @contextmanager
    def limits(*, limits, user_api):
        assert (limits, user_api) == (1, "blas")
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    monkeypatch.setattr(tracking_jobs, "threadpool_limits", limits)
    bad = deepcopy(CALIB)
    bad["image_size"] = [0, 800]
    assert tracking_jobs._calib_summary("bad", bad)["valid"] is False
    assert events == ["enter", "exit"]


def test_calibration_save_list_get(client, env):
    r = client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["valid"] and body["points"] == 4 and body["reprojection_error_m"] < 0.01
    assert (env / "calibrations" / "saha-a.json").exists()
    lst = client.get("/tracking/calibrations").json()
    assert lst["total"] == 1 and lst["calibrations"][0]["name"] == "saha-a"
    got = client.get("/tracking/calibrations/saha-a").json()
    assert got["points"][2]["pitch"] == [105.0, 68.0]


def test_calibration_rejects_invalid(client):
    bad = {"image_size": [10, 10], "points": [{"image": [i, i], "pitch": [i, 0]} for i in range(5)]}
    r = client.post("/tracking/calibrations", json={"name": "bad", "calibration": bad})
    assert r.status_code == 422
    assert client.post("/tracking/calibrations", json={"name": "../x", "calibration": CALIB}).status_code == 422
    assert client.get("/tracking/calibrations/yok").status_code == 404


def test_video_list_and_upload(client, env):
    assert client.get("/tracking/videos").json() == {"videos": [], "total": 0}
    r = client.post("/tracking/videos", files={"file": ("antrenman 1.mp4", b"\x00" * 2048, "video/mp4")})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "antrenman_1.mp4"
    assert (env / "videos" / "antrenman_1.mp4").stat().st_size == 2048
    lst = client.get("/tracking/videos").json()
    assert lst["total"] == 1 and lst["videos"][0]["name"] == "antrenman_1.mp4"
    assert client.post("/tracking/videos", files={"file": ("x.txt", b"abc", "text/plain")}).status_code == 422


def _wait_done(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/tracking/jobs/{job_id}").json()
        if job["state"] in {"done", "failed"}:
            return job
        time.sleep(0.2)
    raise AssertionError(f"iş bitmedi: {client.get(f'/tracking/jobs/{job_id}').json()}")


def test_job_end_to_end_with_stub_worker(client, env, monkeypatch):
    calls = []
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda out_json, tenant_id, match_id: (calls.append((out_json, tenant_id, match_id)) or {"frames_written": 3}))
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00" * 10)
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})

    r = client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "saha-a", "match_id": 990777,
                                            "home_team_id": 11, "away_team_id": 22, "label": "test"})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["state"] in {"queued", "running", "ingesting", "done"}
    assert "command" not in job and "tenant_id" not in job

    done = _wait_done(client, job["id"])
    assert done["state"] == "done", done
    assert done["frames"] == 3 and done["summary"]["tracks"] == 1
    assert done["ingest"] == {"frames_written": 3}
    assert calls and calls[0][1] == "t-default" and calls[0][2] == 990777
    assert any("stub: ok" in ln for ln in done["log_tail"])
    assert Path(done["out_json"]).exists()

    lst = client.get("/tracking/jobs").json()
    assert lst["total"] == 1 and lst["worker_available"] is True

    d = client.delete(f"/tracking/jobs/{job['id']}")
    assert d.status_code == 200
    assert not Path(done["out_json"]).exists()
    assert client.get(f"/tracking/jobs/{job['id']}").status_code == 404


def test_job_is_refused_before_the_worker_starts_when_memory_is_short(client, env, monkeypatch):
    """50 dakika çalışıp çökmek yerine: bellek yetmiyorsa işçi hiç başlamaz, sebep kullanıcıya yazılır."""
    monkeypatch.setenv("TRACKING_MIN_COMMIT_MB", "11000")
    monkeypatch.setattr(tracking_jobs, "system_memory_mb", lambda: {"avail_phys_mb": 4000, "avail_commit_mb": 7500})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00" * 10)
    job = client.post("/tracking/jobs", json={"video": "clip.mp4", "match_id": 990779}).json()
    done = _wait_done(client, job["id"])
    assert done["state"] == "failed"
    assert "bellek yetersiz" in done["error"] and "7.5 GB" in done["error"] and "11 GB" in done["error"]
    assert not any("stub" in ln for ln in done.get("log_tail") or [])


def test_worker_side_memory_refusal_reaches_the_user_as_a_reason_not_an_exit_code(client, env):
    """Büyük karede işçi sarmalayıcısı kendi eşiğiyle reddeder; kullanıcı 'çıkış kodu 5' değil sebebi görür."""
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "bigframe.mp4").write_bytes(b"\x00" * 10)
    job = client.post("/tracking/jobs", json={"video": "bigframe.mp4", "match_id": 990780}).json()
    done = _wait_done(client, job["id"])
    assert done["state"] == "failed"
    assert done["error"].startswith("bellek yetersiz") and "14 GB" in done["error"]


def test_memory_refusal_without_a_readable_reason_still_names_the_cause(tmp_path):
    assert "bellek yetersiz" in tracking_jobs._memory_refusal(tmp_path / "yok.log")


def test_finished_chunks_reach_the_database_while_the_worker_is_still_running(client, env, monkeypatch):
    """Kullanıcı maçın ilk dakikalarını bütün video bitmeden görür; bitişte tam alım yine yapılır."""
    events: list[tuple[str, bool | None]] = []
    seen_running: list[dict] = []
    write_job = tracking_jobs._write_job

    def recording_write(job):
        if job.get("state") == "running" and job.get("progress"):
            seen_running.append(dict(job["progress"]))
        write_job(job)

    monkeypatch.setattr(tracking_jobs, "_write_job", recording_write)
    monkeypatch.setattr(tracking_jobs, "PART_POLL_SECONDS", 0.2)
    monkeypatch.setattr(tracking_jobs, "run_part_ingest",
                        lambda part, tenant, match, *, append: events.append((Path(part).name, append)) or {})
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: events.append(("full", None)) or {"frames_written": 3})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "progressive.mp4").write_bytes(b"\x00" * 10)
    job = client.post("/tracking/jobs", json={"video": "progressive.mp4", "match_id": 990781}).json()
    done = _wait_done(client, job["id"])
    assert done["state"] == "done", done
    # İlk parça eski kareleri siler (append=False), ikincisi ekler; tam alım en sonda gelir.
    assert events == [("ready_0000.json", False), ("ready_0001.json", True), ("full", None)]
    # İş sürerken yazılan son ilerleme iki parçayı da gösterir; iş bitince ilerleme alanı kalkar.
    assert seen_running[-1] == {"chunks_ready": 2, "chunks_total": 2, "chunks_ingested": 2,
                                "frames_ready": 2, "minutes_ready": 5.5, "ingest_errors": 0}
    assert "progress" not in done and done["frames"] == 3
    assert not tracking_jobs.chunk_dir(done["out_json"]).exists()


def test_part_ingest_skips_empty_parts_and_survives_a_failing_one(tmp_path, env, monkeypatch):
    job = {"id": "j1", "tenant_id": "t-default", "match_id": 7, "out_json": str(tmp_path / "job_j1_frames.json"),
           "log": str(tmp_path / "j1.log")}
    folder = tracking_jobs.chunk_dir(job["out_json"])
    folder.mkdir()
    (folder / "ready_0000.json").write_text(json.dumps({"frames": []}), encoding="utf-8")
    (folder / "ready_0001.json").write_text(json.dumps({"frames": [{"minute": 6.2}]}), encoding="utf-8")
    (folder / "ready_0002.json").write_text("{bozuk", encoding="utf-8")
    calls: list[bool] = []
    monkeypatch.setattr(tracking_jobs, "run_part_ingest", lambda *a, append: calls.append(append) or {})
    monkeypatch.setattr(tracking_jobs, "_write_job", lambda job: None)
    seen: set[str] = set()
    tracking_jobs._ingest_ready_parts(job, seen)
    # Boş parça alınmaz; ilk GERÇEK alım yine eski kareleri siler (append=False).
    assert calls == [False]
    assert job["progress"]["chunks_ready"] == 3 and job["progress"]["chunks_ingested"] == 1
    assert job["progress"]["minutes_ready"] == 6.2 and job["progress"]["ingest_errors"] == 1
    assert job["progress"]["chunks_total"] is None
    tracking_jobs._ingest_ready_parts(job, seen)
    assert calls == [False]  # aynı parça ikinci kez alınmaz


def test_job_without_calibration_runs_anchorless(client, env, monkeypatch):
    """Kalibrasyon verilmezse iş ÇAPASIZ başlar: işçiye --calibration geçilmez,
    kalibratör çapayı saha çizgilerinden bulur (TV kuralı)."""
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: {"frames_written": 1})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00" * 10)
    r = client.post("/tracking/jobs", json={"video": "clip.mp4", "match_id": 990778})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["calibration"] is None and job["auto_anchor"] is True
    stored = tracking_jobs._read_job(job["id"])
    assert "--calibration" not in stored["command"]
    done = _wait_done(client, job["id"])
    assert done["state"] == "done", done


def test_jobs_run_one_at_a_time(client, env, monkeypatch):
    """İki iş aynı anda GPU'ya binmez: ikincisi ilki bitene kadar kuyrukta bekler.

    Gerçek işçi yerine `_run_job` zaman damgası kaydeder; aralıkların
    çakışmaması sıralılığın kanıtıdır.
    """
    import threading
    import time as _time

    spans: list[tuple[str, float, float]] = []
    done = threading.Event()

    def fake_run(job):
        t0 = _time.monotonic()
        _time.sleep(0.15)
        spans.append((job["id"], t0, _time.monotonic()))
        if len(spans) == 2:
            done.set()

    monkeypatch.setattr(tracking_jobs, "_run_job", fake_run)
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00" * 10)
    a = client.post("/tracking/jobs", json={"video": "clip.mp4", "match_id": 1}).json()
    b = client.post("/tracking/jobs", json={"video": "clip.mp4", "match_id": 2}).json()
    assert a["state"] == "queued" and b["state"] == "queued"
    assert b["queue_ahead"] >= a["queue_ahead"]
    assert done.wait(5.0), "işler tamamlanmadı"
    (id1, s1, e1), (id2, s2, e2) = sorted(spans, key=lambda t: t[1])
    assert id1 == a["id"] and id2 == b["id"]          # sıra korunur
    assert s2 >= e1, "ikinci iş birincisi bitmeden başladı"


def test_job_failure_is_reported(client, env, monkeypatch):
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: {"frames_written": 0})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "fail.mp4").write_bytes(b"\x00")
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "fail.mp4", "calibration": "saha-a"})
    assert r.status_code == 202
    done = _wait_done(client, r.json()["id"])
    assert done["state"] == "failed" and "3" in done["error"]


def test_job_without_usable_frames_fails_with_reason(client, env, monkeypatch):
    """Sıfır kare 'bitti' görünmemeli: kullanıcı boş sonucu başarı sanar."""
    ingested = []
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: ingested.append(a) or {})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "empty.mp4").write_bytes(b"x")
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "empty.mp4", "calibration": "saha-a"})
    done = _wait_done(client, r.json()["id"])
    assert done["state"] == "failed" and done["frames"] == 0
    assert "319 kare saha çizgilerine oturmadı" in done["error"] and "581 kare tekrar" in done["error"]
    assert ingested == []


def test_job_reports_chunks_that_could_not_be_processed(client, env, monkeypatch):
    """Parça kaybı sessiz kalmamalı: iş biter ama eksik dakikalar söylenir."""
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: {"frames_written": 3})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "partial.mp4").write_bytes(b"x")
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "partial.mp4", "calibration": "saha-a"})
    done = _wait_done(client, r.json()["id"])
    assert done["state"] == "done" and done["warning"].startswith("1/2 parça işlenemedi")


def test_job_runs_the_chunked_worker(client, env, monkeypatch):
    seen = []
    monkeypatch.setattr(tracking_jobs, "enqueue_job", lambda job: seen.append(job["command"]) or 0)
    monkeypatch.delenv("TRACKING_WORKER_CMD")
    monkeypatch.setenv("TRACKING_WORKER_PYTHON", __file__)
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"x")
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    assert client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "saha-a"}).status_code == 202
    assert seen[0][1:5] == ["-m", "scripts.track_video_chunked", "--chunk-seconds", "300.0"]


def test_empty_output_error_without_counters_admits_unknown_reason():
    assert "işçi sebep bildirmedi" in tracking_jobs.empty_output_error(None)


def test_job_validation_errors(client, env):
    assert client.post("/tracking/jobs", json={"video": "yok.mp4", "calibration": "saha-a"}).status_code == 404
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00")
    assert client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "yok"}).status_code == 404
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "saha-a", "weights": str(env / "nope")})
    assert r.status_code == 422


def _live_tele(env, match_id: int, latest: str | None, videos: tuple[str, ...] = ()) -> None:
    tele = env / "live" / str(match_id) / "tele"
    tele.mkdir(parents=True)
    if latest is not None:
        (tele / "latest.json").write_text(latest, encoding="utf-8")
    for stem in videos:
        (tele / f"{stem}.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom")


def test_live_telestration_latest_and_video(client, env):
    _live_tele(env, 990201, json.dumps({"segment": "seg_0003", "summary": {"label": "Orta blok"}}), ("seg_0003",))
    r = client.get("/tracking/live/990201/telestration")
    assert r.status_code == 200
    body = r.json()
    assert body["segment"] == "seg_0003" and body["summary"]["label"] == "Orta blok"
    assert body["video_url"] == "/tracking/live/990201/telestration/seg_0003.mp4"
    v = client.get(body["video_url"])
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4"
    assert v.headers["cache-control"] == "private, no-store"


def test_live_telestration_missing_broken_and_unsafe(client, env):
    assert client.get("/tracking/live/990202/telestration").status_code == 404
    _live_tele(env, 990203, "{yarım")
    assert client.get("/tracking/live/990203/telestration").status_code == 503
    _live_tele(env, 990204, json.dumps({"segment": "../../secret"}))
    assert client.get("/tracking/live/990204/telestration").status_code == 502
    assert client.get("/tracking/live/990204/telestration/seg_99.mp4").status_code == 422
    assert client.get("/tracking/live/990204/telestration/seg_0001.mp4").status_code == 404


def test_live_telestration_keep_up_segment_name(client, env):
    # canli_mac --keep-up adı dakikayı taşır; yol geçişi yine reddedilir
    _live_tele(env, 990205, json.dumps({"segment": "seg_0007_m13.500"}), ("seg_0007_m13.500",))
    body = client.get("/tracking/live/990205/telestration").json()
    assert body["video_url"] == "/tracking/live/990205/telestration/seg_0007_m13.500.mp4"
    assert client.get(body["video_url"]).status_code == 200
    assert client.get("/tracking/live/990205/telestration/seg_0007_m13.5x.mp4").status_code == 422


def test_live_telestration_includes_lag_status(client, env):
    _live_tele(env, 990206, json.dumps({"segment": "seg_0002"}), ("seg_0002",))
    assert client.get("/tracking/live/990206/telestration").json()["status"] is None
    status = {"updated": "2026-11-01T09:00:00+00:00", "stream_minute": 13.0, "processed_minute": 11.5,
              "lag_seconds": 90, "skipped_segments": 2, "keep_up": True, "source_ended": False, "extra": "x"}
    (env / "live" / "990206" / "status.json").write_text(json.dumps(status), encoding="utf-8")
    got = client.get("/tracking/live/990206/telestration").json()["status"]
    assert got["lag_seconds"] == 90.0 and got["skipped_segments"] == 2 and got["keep_up"] is True
    assert "extra" not in got
    # bozuk/eksik durum telestrasyonu düşürmez
    (env / "live" / "990206" / "status.json").write_text(json.dumps({**status, "skipped_segments": True}),
                                                         encoding="utf-8")
    r = client.get("/tracking/live/990206/telestration")
    assert r.status_code == 200 and r.json()["status"] is None


def test_default_weights_prefers_v2_then_mixed(env, monkeypatch) -> None:
    models_dir = env / "models"
    for name in ("rfdetr_mixed_small", "rfdetr_soccertrack_ft_v2"):
        (models_dir / name).mkdir(parents=True)
        (models_dir / name / "meta.json").write_text("{}", encoding="utf-8")
    assert tracking_jobs.default_weights() == str(models_dir / "rfdetr_soccertrack_ft_v2")
    (models_dir / "rfdetr_soccertrack_ft_v2" / "meta.json").unlink()
    assert tracking_jobs.default_weights() == str(models_dir / "rfdetr_mixed_small")
    monkeypatch.setenv("TRACKING_WEIGHTS", "elle")
    assert tracking_jobs.default_weights() == "elle"
