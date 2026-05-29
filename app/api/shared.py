"""Public share endpoint'leri (Faz 5 #40).

Auth'suz erişim — link sahibi token'la sınırlı süre PDF açabilir.
Token formatı `{payload_b64}.{sig_b64}`; doğrulama + expiry check
share.decode_share_token üzerinden. Token bozuk → 400, süresi dolmuş
→ 410, signature uyumsuz → 403.

JWT_SECRET_KEY boşsa servis devre dışı → 503.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
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
    ShareTokenExpired,
    ShareTokenInvalid,
    decode_share_token,
)

router = APIRouter(tags=["public-shared"])


@router.get("/shared/reports/{token}")
def shared_report_pdf(
    token: str,
    session: Session = Depends(get_session),
) -> Response:
    """Auth'suz: imzalı token ile bir AgentOutput PDF'ini sun."""
    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="PDF üretici devre dışı — reportlab kurulu değil",
        )
    secret = get_settings().jwt_secret_key
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Share devre dışı — JWT_SECRET_KEY set'lenmemiş",
        )

    try:
        payload = decode_share_token(token, secret=secret)
    except ShareTokenExpired as e:
        raise HTTPException(status_code=410, detail=str(e)) from e
    except ShareTokenInvalid as e:
        # Token format ya da imza hatalı — public path'te ayrım yapmıyoruz
        raise HTTPException(status_code=403, detail=str(e)) from e

    row = session.execute(
        select(models.AgentOutput).where(
            models.AgentOutput.id == payload.output_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"agent_output {payload.output_id} bulunamadı",
        )

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

    filename = f"{row.agent_name}_{row.subject_type}_{row.subject_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Report-Agent": row.agent_name,
            "X-Report-Subject": f"{row.subject_type}:{row.subject_id}",
            "Cache-Control": "private, no-store",
        },
    )
