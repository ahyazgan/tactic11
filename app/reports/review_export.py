"""Deliver an immutable reviewed snapshot as a portable PDF + playable clips."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import SessionLocal
from app.reports.review_document import CATEGORIES, ReviewDocument, review_time_label, time_label
from app.reports.review_media import asset_path, cut_clip, private_dir
from app.reports.review_pdf import build_review_pdf

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="review-export")
_capacity = threading.BoundedSemaphore(4)
LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 20


def expire_stale(session: Session, tenant_id: str) -> None:
    """Detect interrupted workers on normal status polling, including queued jobs."""
    session.execute(update(models.ReviewExport).where(
        models.ReviewExport.tenant_id == tenant_id,
        models.ReviewExport.state.in_(["queued", "running"]),
        models.ReviewExport.updated_at < datetime.now(UTC) - timedelta(seconds=LEASE_SECONDS),
    ).values(state="failed", error="Hazırlama işlemi kesildi. Teslim paketini yeniden hazırlayın.")
        .execution_options(synchronize_session="fetch"))
    session.commit()


def _heartbeat(export_id: str, tenant_id: str, stop: threading.Event) -> None:
    # Queued work needs a lease too: a long clip must not expire the next job.
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with SessionLocal() as session:
                session.execute(update(models.ReviewExport).where(
                    models.ReviewExport.id == export_id, models.ReviewExport.tenant_id == tenant_id,
                    models.ReviewExport.state.in_(["queued", "running"]),
                ).values(updated_at=datetime.now(UTC)))
                session.commit()
        except Exception:  # noqa: BLE001 — a later poll will expire an unavailable worker
            log.warning("review export heartbeat unavailable: %s", export_id, exc_info=True)


def html_report(snapshot: dict[str, Any]) -> str:
    document = ReviewDocument.model_validate(snapshot["document"])
    e = escape
    scope = "Maçın tamamı incelendi" if document.scope == "full_match" else "Seçilmiş bölümler incelendi"
    parts = ["<!doctype html><html lang='tr'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; media-src 'self'; style-src 'unsafe-inline'\">",
             f"<title>{e(snapshot['title'])}</title>",
             "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#173e38;background:#f6f8f6}article{background:white;padding:24px;border:1px solid #d5e0da;border-radius:12px;margin:24px 0}video{width:100%;max-height:480px;background:#111}p{white-space:pre-wrap}small{color:#53636a}a{color:#176553}</style>",
             f"<h1>{e(snapshot['title'])}</h1><p>{e(document.club)} - {e(document.opponent)}</p>",
             f"<p>{document.match_date or 'Tarih belirtilmedi'} | {scope}</p>",
             f"<small>Kontrol eden: {e(snapshot['reviewer'])} | {review_time_label(snapshot.get('reviewed_at', ''))} | Sürüm {snapshot['version']}</small>",
             "<p><a href='report.pdf'>PDF raporunu aç</a></p>",
             f"<p>{e(document.summary)}</p>", f"<p>{e(document.strengths)}</p>",
             "<h2>Antrenman odağı</h2><ol>"]
    parts.extend(f"<li>{e(action)}</li>" for action in document.training_focus)
    parts.append("</ol><p>Zamanlar kaynak videoya göredir. Bulgular insan gözlemidir.</p>")
    for i, finding in enumerate(document.findings, 1):
        parts.extend([f"<article><h2>{i:02d}. {e(finding.title)}</h2>",
                      f"<small>{CATEGORIES[finding.category]} | {time_label(finding.start)} - {time_label(finding.end)} | {e(finding.player)}</small>",
                      f"<video controls preload='metadata' src='clips/{i:02d}.mp4'></video>",
                      f"<p><b>Gözlem:</b> {e(finding.observation)}</p>",
                      f"<p><b>Çalışma:</b> {e(finding.action)}</p>",
                      f"<p><b>Sonraki kontrol:</b> {e(finding.next_check)}</p></article>"])
    parts.append("<footer>Manager | Kulüp içi kullanım. ZIP dosyasını klasöre çıkarıp index.html dosyasını açın.</footer></html>")
    return "\n".join(parts)


def enqueue_export(export_id: str, tenant_id: str, snapshot: dict[str, Any]) -> bool:
    if not _capacity.acquire(blocking=False):
        return False

    stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(export_id, tenant_id, stop), daemon=True)
    heartbeat.start()

    def run():
        try:
            run_export(export_id, tenant_id, snapshot)
        finally:
            stop.set()
            _capacity.release()
    try:
        _pool.submit(run)
    except RuntimeError:
        stop.set()
        _capacity.release()
        return False
    return True


def run_export(export_id: str, tenant_id: str, snapshot: dict[str, Any]) -> None:
    def set_state(state: str, error: str | None = None):
        with SessionLocal() as session:
            result = session.execute(update(models.ReviewExport).where(
                models.ReviewExport.id == export_id, models.ReviewExport.tenant_id == tenant_id,
                models.ReviewExport.state.in_(["queued", "running"]),
            ).values(state=state, error=error, updated_at=datetime.now(UTC)))
            session.commit()
            return cast(CursorResult, result).rowcount == 1

    output = asset_path(tenant_id, export_id, ".zip")
    temporary = output.with_suffix(".partial.zip")
    work = private_dir(tenant_id) / export_id
    try:
        if not set_state("running"):
            return
        source = asset_path(tenant_id, snapshot["video_id"])
        # Verify immutable source bytes again, not just the original upload metadata.
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != snapshot["source_hash"]:
            raise ValueError("Kaynak video değişti. Raporu yeniden inceleyin.")
        document = ReviewDocument.model_validate(snapshot["document"])
        work.mkdir(exist_ok=True)
        clips = []
        for i, finding in enumerate(document.findings, 1):
            clip = work / f"{i:02d}.mp4"
            cut_clip(source, clip, finding.start, finding.end)
            clips.append(clip)
        pdf = build_review_pdf(title=snapshot["title"], document=document,
                               source=snapshot["source_name"], source_hash=digest,
                               reviewer=snapshot["reviewer"], reviewed_at=snapshot["reviewed_at"],
                               version=snapshot["version"])
        manifest = {**snapshot, "export_id": export_id, "clips": [
            {"file": f"clips/{clip.name}", "sha256": hashlib.sha256(clip.read_bytes()).hexdigest()}
            for clip in clips]}
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("report.pdf", pdf)
            archive.writestr("index.html", html_report(snapshot))
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for clip in clips:
                archive.write(clip, f"clips/{clip.name}")
        temporary.replace(output)
        if not set_state("done"):
            output.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — persist failure and free the worker
        log.exception("review export failed: %s", export_id)
        # Avoid disclosing local paths, command output, or another report's data.
        message = str(exc) if isinstance(exc, ValueError) else "Teslim paketi hazırlanamadı. Kaynak videoyu kontrol edip yeniden deneyin."
        set_state("failed", message[:500])
    finally:
        try:
            temporary.unlink(missing_ok=True)
            # Only files created by this export; never remove source footage.
            if work.exists():
                for clip in work.glob("*.mp4"):
                    clip.unlink(missing_ok=True)
                work.rmdir()
        except OSError:
            log.warning("review export temporary cleanup incomplete: %s", export_id, exc_info=True)
