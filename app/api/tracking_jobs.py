"""Video takibi iş akışı — kalibrasyon, video ve işleme işleri (arayüzden uçtan uca).

GET/POST /tracking/calibrations          — saha kalibrasyonları (JSON, doğrulanır)
GET  /tracking/videos                     — data/tracking/videos altındaki klipler
POST /tracking/videos                     — klip yükle (multipart)
GET  /tracking/videos/{name}/frame        — kalibrasyon için tek kare (JPEG, işçi ile)
POST /tracking/jobs                       — video → TrackingFrame işi başlat
GET  /tracking/jobs, /tracking/jobs/{id}  — durum + log

İşçi: ayrı `venv-cv` yorumlayıcısı (torch) alt süreç olarak `scripts.track_video`
çalıştırır; bitince kareler ana süreçte `ingest_tracking_json` ile DB'ye alınır.
İşler TEK işçiyle sırayla koşar (kuyruk): iki iş aynı anda GPU'ya binmez.
Kalibrasyon isteğe bağlı — verilmezse çapa görüntüden bulunur (TV kuralı).
Durum dosyaları data/tracking/jobs/<id>.json (+ .log) — API yeniden başlasa da
görünür kalır.

Ortam değişkenleri (test/kurulum):
  TRACKING_DATA_DIR        — data/tracking kökü
  TRACKING_WORKER_PYTHON   — işçi yorumlayıcı (varsayılan venv-cv)
  TRACKING_WORKER_CMD      — JSON liste; `[python, -m, scripts.track_video]` yerine
  TRACKING_WEIGHTS         — varsayılan ince ayar ağırlık klasörü
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.core.logging import get_logger
from app.db import models
from app.tracking.calibration import CalibrationError, PitchCalibration

log = get_logger(__name__)
router = APIRouter(prefix="/tracking", tags=["tracking"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
LOG_TAIL_LINES = 30
_jobs_lock = threading.Lock()

# İşler TEK işçiyle SIRAYLA koşar. Her iş kendi iş parçacığında başlatılıyordu:
# iki iş aynı anda GPU'ya biner, bellek dolar (8 GB kartta tek eğitim 7.8 GB
# alıyor), ikisi de çöker ya da sürünür. Kuyruk: ikinci iş "queued" kalır,
# ilki bitince başlar. Kuyruk konumu iş kaydında görünür.
_job_queue: queue.Queue[dict[str, Any]] = queue.Queue()
_worker_started = threading.Lock()
_worker_thread: threading.Thread | None = None


def _worker_loop() -> None:
    while True:
        job = _job_queue.get()
        try:
            _run_job(job)
        except Exception:  # noqa: BLE001 — bir işin hatası kuyruğu öldürmesin
            log.exception("tracking job worker: %s", job.get("id"))
        finally:
            _job_queue.task_done()


def _ensure_worker() -> None:
    global _worker_thread
    with _worker_started:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_worker_loop, daemon=True,
                                              name="tracking-job-worker")
            _worker_thread.start()


def enqueue_job(job: dict[str, Any]) -> int:
    """İşi kuyruğa koy; önünde kaç iş beklediğini döndür. Testlerde monkeypatch edilir."""
    _ensure_worker()
    ahead = _job_queue.qsize()
    _job_queue.put(job)
    return ahead


# --------------------------------------------------------------------------- #
# Yollar / ortam
# --------------------------------------------------------------------------- #


def data_root() -> Path:
    return Path(os.environ.get("TRACKING_DATA_DIR") or PROJECT_ROOT / "data" / "tracking")


def _dir(name: str) -> Path:
    d = data_root() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def worker_python() -> str:
    env = os.environ.get("TRACKING_WORKER_PYTHON")
    if env:
        return env
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return str(PROJECT_ROOT / "venv-cv" / sub)


def worker_cmd(module: str) -> list[str]:
    env = os.environ.get("TRACKING_WORKER_CMD")
    if env:
        return json.loads(env)
    return [worker_python(), "-m", module]


def default_weights() -> str | None:
    """İnce ayarlı ağırlık klasörü — karma (drone + yan açı) tercih edilir."""
    env = os.environ.get("TRACKING_WEIGHTS")
    if env:
        return env
    for name in ("rfdetr_mixed_small", "rfdetr_top_small"):
        cand = data_root() / "models" / name
        if (cand / "meta.json").exists():
            return str(cand)
    return None


def _safe(name: str, what: str) -> str:
    if not SAFE_NAME.match(name) or ".." in name:
        raise HTTPException(status_code=422, detail=f"geçersiz {what} adı: {name!r}")
    return name


def _worker_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUTF8"] = "1"
    return env


# --------------------------------------------------------------------------- #
# Kalibrasyonlar
# --------------------------------------------------------------------------- #


class CalibrationIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    calibration: dict[str, Any]


def _calib_summary(name: str, d: dict[str, Any]) -> dict[str, Any]:
    try:
        c = PitchCalibration.from_dict(d)
        err = round(c.reprojection_error_m, 3)
        valid = True
    except CalibrationError as e:
        err, valid = None, False
        d = {**d, "error": str(e)}
    return {
        "name": name,
        "points": len(d.get("points", [])),
        "image_size": d.get("image_size"),
        "pitch_length_m": d.get("pitch_length_m", 105),
        "pitch_width_m": d.get("pitch_width_m", 68),
        "reprojection_error_m": err,
        "valid": valid,
        "meta": d.get("meta") or {},
    }


@router.get("/calibrations", summary="Saha kalibrasyonları")
def list_calibrations(_user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    out = []
    for p in sorted(_dir("calibrations").glob("*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(_calib_summary(p.stem, json.load(f)))
        except (OSError, ValueError) as e:
            out.append({"name": p.stem, "valid": False, "error": str(e)[:120]})
    return {"calibrations": out, "total": len(out)}


@router.get("/calibrations/{name}", summary="Kalibrasyon JSON'u")
def get_calibration(name: str, _user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    path = _dir("calibrations") / f"{_safe(name, 'kalibrasyon')}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="kalibrasyon yok")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.post("/calibrations", status_code=201, summary="Kalibrasyon kaydet (doğrulanır)")
def save_calibration(body: CalibrationIn, _user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    name = _safe(body.name, "kalibrasyon")
    try:
        calib = PitchCalibration.from_dict(body.calibration)
        err = calib.reprojection_error_m
    except (CalibrationError, KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"kalibrasyon geçersiz: {e}") from e
    path = _dir("calibrations") / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(calib.to_dict(), f, ensure_ascii=False, indent=2)
    return {**_calib_summary(name, calib.to_dict()), "reprojection_error_m": round(err, 3), "path": str(path)}


# --------------------------------------------------------------------------- #
# Videolar
# --------------------------------------------------------------------------- #


def _video_path(name: str) -> Path:
    path = _dir("videos") / _safe(name, "video")
    if not path.exists() or path.suffix.lower() not in VIDEO_EXT:
        raise HTTPException(status_code=404, detail="video yok")
    return path


@router.get("/videos", summary="Yüklü klipler")
def list_videos(_user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    out = []
    for p in sorted(_dir("videos").iterdir()):
        if p.suffix.lower() in VIDEO_EXT and p.is_file():
            st = p.stat()
            out.append({
                "name": p.name,
                "size_mb": round(st.st_size / 1e6, 1),
                "modified": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
            })
    return {"videos": out, "total": len(out)}


@router.post("/videos", status_code=201, summary="Klip yükle")
async def upload_video(
    file: UploadFile = File(...),
    _user: models.User = Depends(get_current_user),
) -> dict[str, Any]:
    raw = Path(file.filename or "clip.mp4").name
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
    if Path(name).suffix.lower() not in VIDEO_EXT:
        raise HTTPException(status_code=422, detail="desteklenen uzantılar: mp4, mov, mkv, avi")
    dest = _dir("videos") / _safe(name, "video")
    size = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(8 * 1024 * 1024):
            out.write(chunk)
            size += len(chunk)
    return {"name": dest.name, "size_mb": round(size / 1e6, 1)}


@router.get("/videos/{name}/frame", summary="Kalibrasyon için tek kare (JPEG)")
def video_frame(
    name: str,
    t: float = Query(1.0, ge=0, le=36000),
    width: int = Query(1920, ge=320, le=3840),
    _user: models.User = Depends(get_current_user),
) -> Response:
    src = _video_path(name)
    cache = _dir("frames") / f"{src.stem}_{t:.2f}_{width}.jpg"
    meta_path = cache.with_suffix(".json")
    if not cache.exists() or not meta_path.exists():
        cmd = [*worker_cmd("scripts.extract_frame"), "--video", str(src), "--t", str(t), "--out", str(cache), "--width", str(width)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=_worker_env(), cwd=str(PROJECT_ROOT))
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HTTPException(status_code=503, detail=f"işçi çalıştırılamadı: {e}") from e
        last = (proc.stdout.strip().splitlines() or [""])[-1]
        try:
            info = json.loads(last)
        except ValueError:
            info = {}
        if proc.returncode != 0 or "error" in info or not cache.exists():
            raise HTTPException(status_code=500, detail=f"kare çıkarılamadı: {info.get('error') or proc.stderr[-300:]}")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(info, f)
    with open(meta_path, encoding="utf-8") as f:
        info = json.load(f)
    headers = {
        "X-Frame-Width": str(info.get("width", "")),
        "X-Frame-Height": str(info.get("height", "")),
        "X-Source-Width": str(info.get("src_width", "")),
        "X-Source-Height": str(info.get("src_height", "")),
        "Cache-Control": "private, max-age=3600",
    }
    return Response(content=cache.read_bytes(), media_type="image/jpeg", headers=headers)


# --------------------------------------------------------------------------- #
# İşler
# --------------------------------------------------------------------------- #


class JobCreate(BaseModel):
    video: str
    # None → çapasız başlangıç: kalibratör çapayı saha çizgilerinden kendisi bulur
    # (TV kuralı; bkz. scripts/track_video.py). Elle kalibrasyon daha doğrudur
    # (ölçüldü: 0.09 m vs ~1.7 m), yayın gibi kalibrasyonu olmayan kaynaklar için.
    calibration: str | None = None
    match_id: int | None = None
    home_team_id: int = 9001
    away_team_id: int = 9002
    label: str | None = Field(default=None, max_length=120)
    fps: float = Field(default=5.0, gt=0, le=30)
    track_fps: float = Field(default=15.0, gt=0, le=60)
    tiles: int = Field(default=6, ge=1, le=10)
    threshold: float = Field(default=0.3, ge=0.05, le=0.95)
    ball_threshold: float = Field(default=0.3, ge=0.05, le=0.95)
    weights: str | None = None
    preview: bool = True
    clip_offset_minutes: float = Field(default=0.0, ge=0, le=130)
    max_seconds: float | None = Field(default=None, gt=0)


def _job_path(job_id: str) -> Path:
    return _dir("jobs") / f"{job_id}.json"


def _write_job(job: dict[str, Any]) -> None:
    job["updated_at"] = datetime.now(UTC).isoformat()
    with _jobs_lock, open(_job_path(job["id"]), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)


def _read_job(job_id: str) -> dict[str, Any] | None:
    p = _job_path(job_id)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def run_ingest(out_json: str, tenant_id: str, match_id: int) -> dict[str, Any]:
    """Kareleri DB'ye al — testlerde monkeypatch edilir."""
    from scripts.ingest_tracking_json import ingest_json

    return ingest_json(path=out_json, tenant_id=tenant_id, match_id=match_id)


def _run_job(job: dict[str, Any]) -> None:
    log_path = Path(job["log"])
    try:
        job["state"] = "running"
        job["started_at"] = datetime.now(UTC).isoformat()
        _write_job(job)
        with open(log_path, "a", encoding="utf-8") as lf:
            proc = subprocess.Popen(  # noqa: S603 — komut sabit liste, kullanıcı girdisi yol değil
                job["command"], stdout=lf, stderr=subprocess.STDOUT,
                env=_worker_env(), cwd=str(PROJECT_ROOT),
            )
            rc = proc.wait()
        if rc != 0 or not Path(job["out_json"]).exists():
            job["state"] = "failed"
            job["error"] = f"işçi çıkış kodu {rc}"
            _write_job(job)
            return
        with open(job["out_json"], encoding="utf-8") as f:
            payload = json.load(f)
        job["summary"] = payload.get("summary")
        job["frames"] = len(payload.get("frames", []))
        job["state"] = "ingesting"
        _write_job(job)
        job["ingest"] = run_ingest(job["out_json"], job["tenant_id"], int(job["match_id"]))
        job["state"] = "done"
        job["finished_at"] = datetime.now(UTC).isoformat()
        _write_job(job)
    except Exception as e:  # noqa: BLE001 — iş durumu kullanıcıya raporlanır
        log.exception("tracking job %s failed", job["id"])
        job["state"] = "failed"
        job["error"] = str(e)[:300]
        _write_job(job)


@router.post("/jobs", status_code=202, summary="Video işleme işi başlat")
def create_job(body: JobCreate, user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    video = _video_path(body.video)
    calib_path: Path | None = None
    if body.calibration:
        calib_path = _dir("calibrations") / f"{_safe(body.calibration, 'kalibrasyon')}.json"
        if not calib_path.exists():
            raise HTTPException(status_code=404, detail="kalibrasyon yok")
    weights = body.weights or default_weights()
    if weights and not (Path(weights) / "meta.json").exists():
        raise HTTPException(status_code=422, detail=f"ağırlık klasörü geçersiz: {weights}")
    if not os.environ.get("TRACKING_WORKER_CMD") and not Path(worker_python()).exists():
        raise HTTPException(status_code=503, detail=f"işçi yorumlayıcı yok: {worker_python()} (venv-cv kurulu değil)")

    job_id = uuid.uuid4().hex[:10]
    match_id = body.match_id or int(time.time())
    out_dir = _dir("out")
    out_json = out_dir / f"job_{job_id}_frames.json"
    preview = out_dir / f"job_{job_id}_preview.mp4" if body.preview else None
    cmd = [
        *worker_cmd("scripts.track_video"),
        "--video", str(video),
        *(["--calibration", str(calib_path)] if calib_path else []),
        "--out", str(out_json),
        "--match-id", str(match_id), "--home-team", str(body.home_team_id), "--away-team", str(body.away_team_id),
        "--fps", str(body.fps), "--track-fps", str(body.track_fps), "--tiles", str(body.tiles),
        "--threshold", str(body.threshold), "--ball-threshold", str(body.ball_threshold),
        "--clip-offset-minutes", str(body.clip_offset_minutes),
    ]
    if weights:
        cmd += ["--weights", weights]
    if preview:
        cmd += ["--preview", str(preview)]
    if body.max_seconds:
        cmd += ["--max-seconds", str(body.max_seconds)]

    job: dict[str, Any] = {
        "id": job_id, "state": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "tenant_id": user.tenant_id, "user": user.email,
        "video": video.name, "calibration": calib_path.stem if calib_path else None,
        "auto_anchor": calib_path is None, "label": body.label,
        "match_id": match_id, "home_team_id": body.home_team_id, "away_team_id": body.away_team_id,
        "params": body.model_dump(exclude={"video", "calibration", "match_id", "label"}),
        "weights": weights, "command": cmd,
        "out_json": str(out_json), "preview": str(preview) if preview else None,
        "log": str(_dir("jobs") / f"{job_id}.log"),
    }
    _write_job(job)
    ahead = enqueue_job(job)
    job["queue_ahead"] = ahead          # bilgi: önünde bekleyen iş sayısı (kayda yazılmaz)
    return _public(job)


def _public(job: dict[str, Any], *, with_log: bool = False) -> dict[str, Any]:
    out = {k: v for k, v in job.items() if k not in {"command", "tenant_id"}}
    if with_log:
        try:
            lines = Path(job["log"]).read_text(encoding="utf-8", errors="replace").splitlines()
            out["log_tail"] = [ln for ln in lines if ln.strip() and "Warning" not in ln][-LOG_TAIL_LINES:]
        except OSError:
            out["log_tail"] = []
    return out


@router.get("/jobs", summary="İşler (en yeni önce)")
def list_jobs(limit: int = Query(50, ge=1, le=200), _user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    jobs = []
    for p in _dir("jobs").glob("*.json"):
        try:
            with open(p, encoding="utf-8") as f:
                jobs.append(_public(json.load(f)))
        except (OSError, ValueError):
            continue
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return {"jobs": jobs[:limit], "total": len(jobs), "worker_python": worker_python(),
            "worker_available": bool(os.environ.get("TRACKING_WORKER_CMD")) or Path(worker_python()).exists(),
            "default_weights": default_weights(), "python": sys.version.split()[0]}


@router.get("/jobs/{job_id}", summary="İş durumu + log")
def get_job(job_id: str, _user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    job = _read_job(_safe(job_id, "iş"))
    if job is None:
        raise HTTPException(status_code=404, detail="iş yok")
    return _public(job, with_log=True)


@router.delete("/jobs/{job_id}", summary="İş kaydını sil (çıktılarıyla)")
def delete_job(job_id: str, _user: models.User = Depends(get_current_user)) -> dict[str, Any]:
    job = _read_job(_safe(job_id, "iş"))
    if job is None:
        raise HTTPException(status_code=404, detail="iş yok")
    if job.get("state") in {"queued", "running", "ingesting"}:
        raise HTTPException(status_code=409, detail="iş çalışıyor")
    for key in ("out_json", "preview", "log"):
        p = job.get(key)
        if p and Path(p).exists():
            Path(p).unlink()
    _job_path(job["id"]).unlink(missing_ok=True)
    shutil.rmtree(_dir("frames") / job["id"], ignore_errors=True)
    return {"deleted": job["id"]}
