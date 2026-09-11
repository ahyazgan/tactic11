"""/tracking kalibrasyon, video ve iş uçları — işçi stub ile uçtan uca."""
from __future__ import annotations

import json
import sys
import time
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


def test_job_failure_is_reported(client, env, monkeypatch):
    monkeypatch.setattr(tracking_jobs, "run_ingest", lambda *a, **k: {"frames_written": 0})
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "fail.mp4").write_bytes(b"\x00")
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "fail.mp4", "calibration": "saha-a"})
    assert r.status_code == 202
    done = _wait_done(client, r.json()["id"])
    assert done["state"] == "failed" and "3" in done["error"]


def test_job_validation_errors(client, env):
    assert client.post("/tracking/jobs", json={"video": "yok.mp4", "calibration": "saha-a"}).status_code == 404
    (env / "videos").mkdir(parents=True, exist_ok=True)
    (env / "videos" / "clip.mp4").write_bytes(b"\x00")
    assert client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "yok"}).status_code == 404
    client.post("/tracking/calibrations", json={"name": "saha-a", "calibration": CALIB})
    r = client.post("/tracking/jobs", json={"video": "clip.mp4", "calibration": "saha-a", "weights": str(env / "nope")})
    assert r.status_code == 422
