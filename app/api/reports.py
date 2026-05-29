"""PDF rapor endpoint'leri (Faz 5 #16, #40).

- GET /reports/agent-outputs/{id}/pdf — bir AgentOutput'tan PDF üretir
- GET /reports/agents/{name}/{type}/{id}/pdf — agent + subject ile son output
- POST /reports/agent-outputs/{id}/share — paylaşılabilir kısa token (#40)

reportlab yoksa PDF endpoint'leri 503; share endpoint ek olarak
JWT_SECRET_KEY ister.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models
from app.db.session import get_session
from app.reports.pdf import (
    REPORTLAB_AVAILABLE,
    ReportlabNotInstalled,
    build_agent_output_pdf,
)
from app.reports.share import (
    DEFAULT_TTL_HOURS,
    MAX_TTL_HOURS,
    ShareTokenError,
    encode_share_token,
)

router = APIRouter(tags=["reports"])


def _ensure_reportlab() -> None:
    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "PDF üretici devre dışı — reportlab kurulu değil. "
                "`pip install reportlab>=4.0`"
            ),
        )


def _build_pdf_response(row: models.AgentOutput) -> Response:
    try:
        pdf_bytes = build_agent_output_pdf(
            agent_name=row.agent_name,
            agent_version=row.agent_version,
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            summary=row.summary,
            output_json=row.output_json,
            updated_at=row.updated_at,
        )
    except ReportlabNotInstalled as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=500, detail=f"PDF üretim hatası: {e}",
        ) from e

    filename = (
        f"{row.agent_name}_{row.subject_type}_{row.subject_id}.pdf"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Report-Agent": row.agent_name,
            "X-Report-Subject": f"{row.subject_type}:{row.subject_id}",
        },
    )


@router.get("/reports/agent-outputs/{output_id}/pdf")
def agent_output_pdf(
    output_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Bir AgentOutput satırını PDF olarak indir/aç."""
    _ensure_reportlab()
    row = session.execute(
        select(models.AgentOutput).where(models.AgentOutput.id == output_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"agent_output {output_id} bulunamadı",
        )
    return _build_pdf_response(row)


@router.get(
    "/reports/agents/{agent_name}/{subject_type}/{subject_id}/pdf"
)
def latest_agent_output_pdf(
    agent_name: str,
    subject_type: str,
    subject_id: int,
    agent_version: str | None = None,
    session: Session = Depends(get_session),
) -> Response:
    """Agent + subject ile (en son) AgentOutput'u PDF olarak döndür.

    `agent_version` verilirse o sürümü, yoksa updated_at en yeni satırı."""
    _ensure_reportlab()
    q = select(models.AgentOutput).where(
        models.AgentOutput.agent_name == agent_name,
        models.AgentOutput.subject_type == subject_type,
        models.AgentOutput.subject_id == subject_id,
    )
    if agent_version is not None:
        q = q.where(models.AgentOutput.agent_version == agent_version)
    q = q.order_by(models.AgentOutput.updated_at.desc()).limit(1)
    row = session.execute(q).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"agent_output yok: {agent_name} / {subject_type} #{subject_id}"
            ),
        )
    return _build_pdf_response(row)


@router.post("/reports/agent-outputs/{output_id}/share")
def create_share_link(
    output_id: int,
    request: Request,
    ttl_hours: int = Query(DEFAULT_TTL_HOURS, ge=1, le=MAX_TTL_HOURS),
    session: Session = Depends(get_session),
) -> dict:
    """Bir AgentOutput PDF'i için paylaşılabilir kısa token üret.

    Token public `/shared/reports/{token}` üzerinden auth'suz okunur;
    `ttl_hours` (1..720, default 24) içinde geçerli. Imza HMAC-SHA256;
    server-side secret JWT_SECRET_KEY.
    """
    secret = get_settings().jwt_secret_key
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Share devre dışı — JWT_SECRET_KEY set'lenmemiş",
        )

    row = session.execute(
        select(models.AgentOutput).where(models.AgentOutput.id == output_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"agent_output {output_id} bulunamadı",
        )

    try:
        token = encode_share_token(
            output_id, secret=secret, ttl_hours=ttl_hours,
        )
    except ShareTokenError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    base = str(request.base_url).rstrip("/")
    return {
        "output_id": output_id,
        "token": token,
        "url": f"{base}/shared/reports/{token}",
        "ttl_hours": ttl_hours,
    }
