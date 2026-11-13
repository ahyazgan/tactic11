"""Ürün tam maç sınavı: kullanıcının yükleme yolunu (POST /tracking/jobs) baştan sona koşar.

Ön kayıt ve şartlar: docs/measurements/product-full-match-exam-preregistration.json.
Yöntem kodu değiştirmez; yalnız iş ucunu çağırır, çıktıyı ölçer ve geçti/kaldı yazar.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.system_resources import system_memory_mb

GATES: dict[str, float] = {
    "max_processing_ratio": 5.0,
    "min_minute_coverage": 0.95,
    "min_median_players": 16.0,
    "min_frames_8plus_share": 0.80,
    "min_shape_ok_share": 0.90,
    "min_free_disk_gb": 3.0,
}
TERMINAL = {"done", "failed"}
SHAPE_STEP_MINUTES = 5
REVIEW_SEED = 20261103
REVIEW_SAMPLES = 20


def frame_metrics(frames: list[dict[str, Any]], expected_seconds: float) -> dict[str, Any]:
    """Çıktı karelerinden kapsama ve oyuncu sayısı; kare yoksa sıfır döner, uydurmaz."""
    counts = [len(f.get("players") or []) for f in frames]
    expected_minutes = max(1, int(expected_seconds // 60))
    minutes = {int(f["minute"]) for f in frames if f.get("minute") is not None}
    covered = sum(1 for m in range(expected_minutes) if m in minutes)
    return {
        "frames": len(frames),
        "expected_minutes": expected_minutes,
        "covered_minutes": covered,
        "minute_coverage": covered / expected_minutes,
        "median_players": statistics.median(counts) if counts else 0.0,
        "frames_8plus_share": sum(c >= 8 for c in counts) / len(counts) if counts else 0.0,
        "ball_share": sum(bool(f.get("ball")) for f in frames) / len(frames) if frames else 0.0,
    }


def evaluate(result: dict[str, Any], gates: dict[str, float] = GATES) -> dict[str, Any]:
    """Şartları tek tek değerlendirir. Ölçülemeyen şart geçmiş sayılmaz."""
    m = result.get("metrics") or {}
    checks = {
        "job_done": result.get("job_state") == "done",
        "ingest_complete": bool(m.get("frames")) and result.get("status_frames") == m.get("frames"),
        "processing_ratio": (result.get("processing_ratio") or float("inf")) <= gates["max_processing_ratio"],
        "minute_coverage": m.get("minute_coverage", 0.0) >= gates["min_minute_coverage"],
        "median_players": m.get("median_players", 0.0) >= gates["min_median_players"],
        "frames_8plus_share": m.get("frames_8plus_share", 0.0) >= gates["min_frames_8plus_share"],
        "shape_ok_share": result.get("shape_ok_share", 0.0) >= gates["min_shape_ok_share"],
        "free_disk": result.get("min_free_disk_gb", 0.0) >= gates["min_free_disk_gb"],
    }
    return {"checks": checks, "automatic_gates_passed": all(checks.values())}


def _shape_ok(body: dict[str, Any]) -> bool:
    teams = body.get("teams") or {}
    return bool(teams) and all((t or {}).get("shape") for t in teams.values())


def probe_product(client: Any, match_id: int, expected_seconds: float) -> dict[str, Any]:
    """Panelin kullandığı uçları çağırır; hata kodunu saklar, yutmaz."""
    status = client.get(f"/tracking/matches/{match_id}/status")
    minutes = range(SHAPE_STEP_MINUTES, int(expected_seconds // 60) + 1, SHAPE_STEP_MINUTES)
    shape_codes: list[int] = []
    shape_ok = 0
    for minute in minutes:
        r = client.get(f"/tracking/matches/{match_id}/shape", params={"minute": min(minute, 130)})
        shape_codes.append(r.status_code)
        shape_ok += r.status_code == 200 and _shape_ok(r.json())
    return {
        "status_http": status.status_code,
        "status_frames": status.json().get("frames") if status.status_code == 200 else None,
        "shape_probes": len(shape_codes),
        "shape_error_codes": sorted({c for c in shape_codes if c != 200}),
        "shape_ok_share": shape_ok / len(shape_codes) if shape_codes else 0.0,
    }


def review_sample(frames: list[dict[str, Any]]) -> list[float]:
    """Elle kontrol edilecek kareler: tohum ön kayıtlı, sonuç görülmeden sabit."""
    minutes = sorted(f["minute"] for f in frames if f.get("minute") is not None)
    return sorted(random.Random(REVIEW_SEED).sample(minutes, min(REVIEW_SAMPLES, len(minutes))))


def _free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def _kill_tree() -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(os.getpid())], check=False)  # noqa: S603, S607
    sys.exit(2)


def run_exam(client: Any, args: argparse.Namespace, data_dir: Path) -> dict[str, Any]:
    """İşi başlatır, bitene kadar izler, ürün uçlarını yoklar ve sonucu döndürür."""
    body: dict[str, Any] = {"video": args.video, "calibration": args.calibration, "match_id": args.match_id}
    if args.max_seconds:
        body["max_seconds"] = args.max_seconds
    expected = args.max_seconds or args.expected_seconds
    started = time.monotonic()
    result: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(), "video": args.video, "calibration": args.calibration,
        "expected_seconds": expected, "gates": GATES,
    }
    created = client.post("/tracking/jobs", json=body)
    created.raise_for_status()
    job_id = created.json()["id"]
    free = _free_gb(data_dir)
    memory_start = system_memory_mb()
    memory_min = dict(memory_start) if memory_start else None
    job: dict[str, Any] = created.json()
    while job.get("state") not in TERMINAL:
        time.sleep(args.poll_seconds)
        job = client.get(f"/tracking/jobs/{job_id}").json()
        free = min(free, _free_gb(data_dir))
        now = system_memory_mb()
        if now and memory_min:
            memory_min = {k: min(memory_min[k], v) for k, v in now.items()}
        if free < GATES["min_free_disk_gb"]:
            result.update(job_state="aborted_low_disk", min_free_disk_gb=free)
            _write(args.out, result)
            _kill_tree()
    elapsed = time.monotonic() - started
    result.update(
        job_id=job_id, job_state=job.get("state"), job_error=job.get("error"), elapsed_seconds=round(elapsed, 1),
        processing_ratio=round(elapsed / expected, 3), min_free_disk_gb=round(free, 2),
        job_summary=job.get("summary"), log_tail=(job.get("log_tail") or [])[-5:],
        job_warning=job.get("warning"), system_memory_start=memory_start, system_memory_min=memory_min,
    )
    out_json = data_dir / "out" / f"job_{job_id}_frames.json"
    if job.get("state") == "done" and out_json.exists():
        with open(out_json, encoding="utf-8") as f:
            frames = json.load(f).get("frames", [])
        result["metrics"] = frame_metrics(frames, expected)
        result["review_minutes"] = review_sample(frames)
        result["outputs_mb"] = {
            p.name: round(p.stat().st_size / 1e6, 1) for p in (data_dir / "out").glob(f"job_{job_id}_*")
        }
        result.update(probe_product(client, args.match_id, expected))
    result["finished_at"] = datetime.now(UTC).isoformat()
    result["verdict"] = evaluate(result)
    return result


def _write(path: str, result: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def _build_client(database: str) -> Any:
    """Sınava ayrı SQLite; demo.db ve .env'deki DSN'e dokunulmaz. Giriş ekranı sınav dışı."""
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(database).resolve().as_posix()}"
    from fastapi.testclient import TestClient

    from app.api.auth import get_current_user
    from app.api.main import app
    from app.db import models
    from app.db.base import Base
    from app.db.session import SessionLocal, engine, get_session

    Base.metadata.create_all(engine)
    session = SessionLocal()
    session.info["tenant_id"] = "t-default"
    if session.get(models.Tenant, "t-default") is None:
        now = datetime.now(UTC)
        session.add(models.Tenant(id="t-default", slug="t-default", name="Sınav", settings_json="{}",
                                  active=True, created_at=now))
        session.add(models.User(id="exam", tenant_id="t-default", email="exam@local", password_hash="x",
                                role="admin", active=True, created_at=now))
        session.commit()

    def _session():
        yield session
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: session.get(models.User, "exam")
    return TestClient(app)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", required=True, help="data/tracking/videos altındaki dosya adı")
    p.add_argument("--calibration", default=None, help="kalibrasyon adı (uzantısız)")
    p.add_argument("--expected-seconds", type=float, required=True, help="videonun süresi")
    p.add_argument("--max-seconds", type=float, default=None, help="yalnız prova; sınavda verilmez")
    p.add_argument("--match-id", type=int, required=True)
    p.add_argument("--database", required=True, help="sınava ayrılmış SQLite dosyası")
    p.add_argument("--out", required=True)
    p.add_argument("--poll-seconds", type=float, default=30.0)
    args = p.parse_args()
    client = _build_client(args.database)
    from app.api.tracking_jobs import data_root

    result = run_exam(client, args, data_root())
    _write(args.out, result)
    print(json.dumps(result["verdict"], ensure_ascii=False))
    return 0 if result["verdict"]["automatic_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
