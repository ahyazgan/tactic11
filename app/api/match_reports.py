"""Authenticated, tenant-isolated, human-reviewed match reporting."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_tenant, get_current_user, require_role
from app.core.config import get_settings
from app.db import models
from app.db.session import get_session
from app.reports import review_export, review_media
from app.reports.review_document import ReviewDocument
from app.reports.review_pdf import build_review_pdf

router = APIRouter(prefix="/match-reports", tags=["match-reports"], dependencies=[Depends(get_current_tenant)])
playback_router = APIRouter(tags=["match-report-playback"])
editor = require_role(["admin", "analyst", "coach"])
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                   "Referrer-Policy": "no-referrer"}
_dev_playback_secret = secrets.token_urlsafe(32)


def _playback_secret() -> str:
    # Separate signing domain: a media token can never act as an account token.
    secret = get_settings().jwt_secret_key or _dev_playback_secret
    return hashlib.sha256(("review-playback:" + secret).encode()).hexdigest()


def _delivery_secret() -> str:
    secret = get_settings().jwt_secret_key or _dev_playback_secret
    return hashlib.sha256(("review-delivery:" + secret).encode()).hexdigest()


def _media_user(claims: dict[str, Any], session: Session) -> models.User:
    user = session.get(models.User, claims["sub"])
    if not user or not user.active or user.tenant_id != claims["tenant"]:
        raise HTTPException(401, "Dosya erişimi geçersiz.")
    tenant = session.get(models.Tenant, user.tenant_id)
    if not tenant or not tenant.active:
        raise HTTPException(401, "Kulüp erişimi kapalı.")
    # Signed media requests have no bearer header. Override the local development
    # default only after validating the signature, account and club.
    session.info["tenant_id"] = user.tenant_id
    return user


class ReportCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    video_id: uuid.UUID
    title: str = Field(min_length=1, max_length=180)
    document: ReviewDocument = Field(default_factory=ReviewDocument)


class ReportSave(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    document: ReviewDocument


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


def _video(session: Session, user: models.User, video_id: str) -> models.ReviewVideo:
    row = session.execute(select(models.ReviewVideo).where(
        models.ReviewVideo.id == video_id, models.ReviewVideo.tenant_id == user.tenant_id,
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Video bulunamadı.")
    return row


def _report(session: Session, user: models.User, report_id: str) -> models.MatchReviewReport:
    row = session.execute(select(models.MatchReviewReport).where(
        models.MatchReviewReport.id == report_id, models.MatchReviewReport.tenant_id == user.tenant_id,
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Rapor bulunamadı.")
    return row


def _utc(value: datetime | None) -> str | None:
    # SQLite drops tzinfo even on timezone=True columns; never send ambiguous
    # local timestamps to the browser or into the delivery manifest.
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def _out(row: models.MatchReviewReport) -> dict[str, Any]:
    return {"id": row.id, "title": row.title, "video_id": row.video_id, "version": row.version,
            "document": json.loads(row.document_json), "reviewed_at": _utc(row.reviewed_at),
            "reviewed_by": row.reviewed_by, "updated_at": _utc(row.updated_at)}


def _approved(row: models.MatchReviewReport) -> None:
    if not row.reviewed_at or not row.reviewed_by:
        raise HTTPException(409, "Teslimden önce raporu inceleyip onaylayın.")


def _snapshot(row: models.MatchReviewReport, video: models.ReviewVideo, session: Session) -> dict[str, Any]:
    reviewer = session.get(models.User, row.reviewed_by) if row.reviewed_by else None
    return {"report_id": row.id, "title": row.title, "version": row.version,
            "document": json.loads(row.document_json), "video_id": video.id,
            "source_name": video.filename, "source_hash": video.sha256,
            "source_duration": video.duration_seconds,
            "reviewer": reviewer.email if reviewer else "Kayıtlı analist",
            "reviewed_at": _utc(row.reviewed_at) or ""}


@router.get("/videos")
def list_videos(user: models.User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.scalars(select(models.ReviewVideo).where(
        models.ReviewVideo.tenant_id == user.tenant_id,
    ).order_by(models.ReviewVideo.created_at.desc()).limit(100)).all()
    return [{"id": r.id, "filename": r.filename, "duration_seconds": r.duration_seconds,
             "size_bytes": r.size_bytes, "created_at": r.created_at} for r in rows]


@router.post("/videos", status_code=201)
async def upload_video(file: UploadFile, user: models.User = Depends(editor),
                       session: Session = Depends(get_session)):
    filename = Path((file.filename or "video.mp4").replace("\\", "/")).name[:255]
    if Path(filename).suffix.lower() != ".mp4":
        raise HTTPException(422, "İlk pilot için MP4 video yükleyin.")
    video_id = str(uuid.uuid4())
    destination = review_media.asset_path(user.tenant_id, video_id)
    temporary = destination.with_suffix(".upload")
    limit = int(os.environ.get("REVIEW_MAX_UPLOAD_BYTES", str(2 * 1024 ** 3)))
    digest, size = hashlib.sha256(), 0
    try:
        with temporary.open("xb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "Video yükleme sınırını aşıyor.")
                digest.update(chunk)
                await run_in_threadpool(stream.write, chunk)
        duration = await run_in_threadpool(review_media.probe_video, temporary)
        temporary.replace(destination)
        row = models.ReviewVideo(id=video_id, tenant_id=user.tenant_id, filename=filename,
                                 sha256=digest.hexdigest(), size_bytes=size,
                                 duration_seconds=duration, created_at=datetime.now(UTC))
        session.add(row)
        session.commit()
    except review_media.MediaError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    except BaseException:
        session.rollback()
        destination.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        await file.close()
    return {"id": video_id, "filename": filename, "duration_seconds": duration, "size_bytes": size}


@router.get("/videos/{video_id}/content")
def video_content(video_id: uuid.UUID, user: models.User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    _video(session, user, str(video_id))
    path = review_media.asset_path(user.tenant_id, str(video_id))
    if not path.is_file():
        raise HTTPException(404, "Kaynak video dosyası bulunamadı.")
    return FileResponse(path, media_type="video/mp4", headers=PRIVATE_HEADERS)


@router.post("/videos/{video_id}/playback")
def playback_url(video_id: uuid.UUID, user: models.User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    _video(session, user, str(video_id))
    now = datetime.now(UTC)
    token = jwt.encode({"sub": user.id, "tenant": user.tenant_id, "video": str(video_id),
                        "aud": "review-video", "iat": now, "exp": now + timedelta(hours=4)},
                       _playback_secret(), algorithm="HS256")
    return {"path": f"/review-media/{video_id}?access={token}"}


@playback_router.get("/review-media/{video_id}")
def play_video(video_id: uuid.UUID, access: str = Query(min_length=1, max_length=2048),
               session: Session = Depends(get_session)):
    try:
        claims = jwt.decode(access, _playback_secret(), algorithms=["HS256"], audience="review-video",
                            options={"require": ["exp", "iat", "sub", "video", "tenant"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Video erişiminin süresi doldu; raporu yeniden açın.") from exc
    if claims["video"] != str(video_id):
        raise HTTPException(401, "Video erişimi geçersiz.")
    user = _media_user(claims, session)
    return video_content(video_id, user, session)


@router.get("")
def list_reports(user: models.User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.scalars(select(models.MatchReviewReport).where(
        models.MatchReviewReport.tenant_id == user.tenant_id,
    ).order_by(models.MatchReviewReport.updated_at.desc()).limit(100)).all()
    return [_out(row) for row in rows]


@router.post("", status_code=201)
def create_report(body: ReportCreate, user: models.User = Depends(editor), session: Session = Depends(get_session)):
    video = _video(session, user, str(body.video_id))
    if any(f.end > video.duration_seconds for f in body.document.findings):
        raise HTTPException(422, "Pozisyon aralığı kaynak video süresini aşamaz.")
    now = datetime.now(UTC)
    row = models.MatchReviewReport(id=str(uuid.uuid4()), tenant_id=user.tenant_id,
                                   video_id=str(body.video_id), title=body.title,
                                   document_json=body.document.model_dump_json(), version=1,
                                   created_at=now, updated_at=now)
    session.add(row)
    session.commit()
    return _out(row)


@router.get("/{report_id}")
def get_report(report_id: uuid.UUID, user: models.User = Depends(get_current_user), session: Session = Depends(get_session)):
    return _out(_report(session, user, str(report_id)))


@router.put("/{report_id}")
def save_report(report_id: uuid.UUID, body: ReportSave, user: models.User = Depends(editor),
                session: Session = Depends(get_session)):
    row = _report(session, user, str(report_id))
    video = _video(session, user, row.video_id)
    if any(f.end > video.duration_seconds for f in body.document.findings):
        raise HTTPException(422, "Pozisyon aralığı kaynak video süresini aşamaz.")
    result = session.execute(update(models.MatchReviewReport).where(
        models.MatchReviewReport.id == row.id, models.MatchReviewReport.tenant_id == user.tenant_id,
        models.MatchReviewReport.version == body.version,
    ).values(title=body.title, document_json=body.document.model_dump_json(),
             version=body.version + 1, reviewed_by=None, reviewed_at=None, updated_at=datetime.now(UTC)))
    if cast(CursorResult, result).rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Rapor başka bir oturumda değişti. Yeniden yükleyin; notlarınızı koruyun.")
    session.commit()
    session.refresh(row)
    return _out(row)


@router.post("/{report_id}/approve")
def approve_report(report_id: uuid.UUID, body: VersionIn, user: models.User = Depends(editor),
                   session: Session = Depends(get_session)):
    row = _report(session, user, str(report_id))
    document = ReviewDocument.model_validate_json(row.document_json)
    if not document.summary or not document.findings or not document.training_focus:
        raise HTTPException(422, "Özet, en az bir pozisyon ve antrenman odağı gerekli.")
    now = datetime.now(UTC)
    result = session.execute(update(models.MatchReviewReport).where(
        models.MatchReviewReport.id == row.id, models.MatchReviewReport.tenant_id == user.tenant_id,
        models.MatchReviewReport.version == body.version,
    ).values(reviewed_by=user.id, reviewed_at=now, updated_at=now, version=body.version + 1))
    if cast(CursorResult, result).rowcount != 1:
        session.rollback()
        raise HTTPException(409, "Rapor değişti. Son sürümü inceleyip onaylayın.")
    session.commit()
    session.refresh(row)
    return _out(row)


@router.get("/{report_id}/pdf")
def download_pdf(report_id: uuid.UUID, user: models.User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    row = _report(session, user, str(report_id))
    _approved(row)
    snapshot = _snapshot(row, _video(session, user, row.video_id), session)
    pdf = build_review_pdf(title=row.title, document=ReviewDocument.model_validate(snapshot["document"]),
                           source=snapshot["source_name"], source_hash=snapshot["source_hash"],
                           reviewer=snapshot["reviewer"], reviewed_at=snapshot["reviewed_at"], version=row.version)
    return Response(pdf, media_type="application/pdf", headers={**PRIVATE_HEADERS,
                    "Content-Disposition": f'attachment; filename="match-report-{row.id}.pdf"'})


@router.post("/{report_id}/exports", status_code=202)
def create_export(report_id: uuid.UUID, body: VersionIn, user: models.User = Depends(editor),
                  session: Session = Depends(get_session)):
    row = _report(session, user, str(report_id))
    _approved(row)
    if row.version != body.version:
        raise HTTPException(409, "Teslim için son onaylanan rapor sürümünü seçin.")
    review_export.expire_stale(session, user.tenant_id)
    active = session.scalars(select(models.ReviewExport).where(
        models.ReviewExport.tenant_id == user.tenant_id,
        models.ReviewExport.state.in_(["queued", "running"]),
    )).all()
    now = datetime.now(UTC)
    if active:
        raise HTTPException(409, "Kulübünüzün bir teslim paketi hazırlanıyor; tamamlanmasını bekleyin.")
    snapshot = _snapshot(row, _video(session, user, row.video_id), session)
    job = models.ReviewExport(id=str(uuid.uuid4()), tenant_id=user.tenant_id, report_id=row.id,
                              report_version=row.version, state="queued", created_at=now, updated_at=now)
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Kulübünüzün bir teslim paketi hazırlanıyor; tamamlanmasını bekleyin.") from exc
    if not review_export.enqueue_export(job.id, user.tenant_id, snapshot):
        job.state, job.error = "failed", "Teslim kuyruğu dolu; biraz sonra yeniden deneyin."
        session.commit()
        raise HTTPException(503, job.error)
    return {"id": job.id, "state": "queued", "report_version": row.version}


def _export(session: Session, user: models.User, report_id: str, export_id: str):
    job = session.scalars(select(models.ReviewExport).where(
        models.ReviewExport.id == export_id, models.ReviewExport.report_id == report_id,
        models.ReviewExport.tenant_id == user.tenant_id,
    )).first()
    if job is None:
        raise HTTPException(404, "Teslim paketi bulunamadı.")
    return job


@router.get("/{report_id}/exports")
def list_exports(report_id: uuid.UUID, user: models.User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    _report(session, user, str(report_id))
    review_export.expire_stale(session, user.tenant_id)
    rows = session.scalars(select(models.ReviewExport).where(
        models.ReviewExport.report_id == str(report_id), models.ReviewExport.tenant_id == user.tenant_id,
    ).order_by(models.ReviewExport.created_at.desc()).limit(10)).all()
    return [{"id": row.id, "state": row.state, "error": row.error, "report_version": row.report_version}
            for row in rows]


@router.get("/{report_id}/exports/{export_id}")
def export_status(report_id: uuid.UUID, export_id: uuid.UUID, user: models.User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    review_export.expire_stale(session, user.tenant_id)
    job = _export(session, user, str(report_id), str(export_id))
    return {"id": job.id, "state": job.state, "error": job.error, "report_version": job.report_version}


@router.get("/{report_id}/exports/{export_id}/download")
def export_download(report_id: uuid.UUID, export_id: uuid.UUID, user: models.User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    job = _export(session, user, str(report_id), str(export_id))
    path = review_media.asset_path(user.tenant_id, job.id, ".zip")
    if job.state != "done" or not path.is_file():
        raise HTTPException(409, "Teslim paketi henüz hazır değil.")
    return FileResponse(path, media_type="application/zip", filename=f"match-report-v{job.report_version}.zip",
                        headers=PRIVATE_HEADERS)


@router.post("/{report_id}/exports/{export_id}/download-link")
def export_download_link(report_id: uuid.UUID, export_id: uuid.UUID, user: models.User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
    # Check readiness and ownership before issuing a narrowly scoped capability.
    export_download(report_id, export_id, user, session)
    now = datetime.now(UTC)
    token = jwt.encode({"sub": user.id, "tenant": user.tenant_id, "report": str(report_id),
                        "export": str(export_id), "aud": "review-delivery", "iat": now,
                        "exp": now + timedelta(minutes=2)}, _delivery_secret(), algorithm="HS256")
    return {"path": f"/review-media/exports/{export_id}?access={token}"}


@playback_router.get("/review-media/exports/{export_id}")
def download_delivery(export_id: uuid.UUID, access: str = Query(min_length=1, max_length=2048),
                      session: Session = Depends(get_session)):
    try:
        claims = jwt.decode(access, _delivery_secret(), algorithms=["HS256"], audience="review-delivery",
                            options={"require": ["exp", "iat", "sub", "tenant", "report", "export"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "İndirme erişiminin süresi doldu; ZIP indir düğmesine yeniden basın.") from exc
    if claims["export"] != str(export_id):
        raise HTTPException(401, "İndirme erişimi geçersiz.")
    user = _media_user(claims, session)
    return export_download(uuid.UUID(claims["report"]), export_id, user, session)
