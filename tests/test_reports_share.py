"""PDF share token + public share endpoint testleri (Faz 5 #40)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.reports.pdf import REPORTLAB_AVAILABLE
from app.reports.share import (
    DEFAULT_TTL_HOURS,
    MAX_TTL_HOURS,
    ShareTokenError,
    ShareTokenExpired,
    ShareTokenInvalid,
    decode_share_token,
    encode_share_token,
)


SECRET = "test-secret-32-byte-random-abcdefgh"


# --------------------------------------------------------------------------- #
# Saf token encode/decode
# --------------------------------------------------------------------------- #


def test_encode_token_format() -> None:
    token = encode_share_token(42, secret=SECRET)
    assert "." in token
    payload_b64, sig_b64 = token.rsplit(".", 1)
    assert payload_b64
    assert sig_b64


def test_round_trip_decodes_output_id() -> None:
    token = encode_share_token(123, secret=SECRET, ttl_hours=1)
    payload = decode_share_token(token, secret=SECRET)
    assert payload.output_id == 123
    assert payload.expires_at > datetime.now(UTC)


def test_decode_rejects_tampered_signature() -> None:
    token = encode_share_token(42, secret=SECRET)
    bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(ShareTokenInvalid):
        decode_share_token(bad, secret=SECRET)


def test_decode_rejects_wrong_secret() -> None:
    token = encode_share_token(42, secret=SECRET)
    with pytest.raises(ShareTokenInvalid):
        decode_share_token(token, secret="başka-secret")


def test_decode_rejects_malformed_token() -> None:
    with pytest.raises(ShareTokenInvalid):
        decode_share_token("notatoken", secret=SECRET)


def test_decode_rejects_empty_token() -> None:
    with pytest.raises(ShareTokenInvalid):
        decode_share_token("", secret=SECRET)


def test_decode_rejects_expired_token() -> None:
    past = datetime.now(UTC) - timedelta(hours=2)
    # Üretim sırasında now'ı geçmişe sapt, TTL 1 saat — token zaten dolmuş
    token = encode_share_token(42, secret=SECRET, ttl_hours=1, now=past)
    with pytest.raises(ShareTokenExpired):
        decode_share_token(token, secret=SECRET)


def test_encode_rejects_empty_secret() -> None:
    with pytest.raises(ShareTokenError):
        encode_share_token(42, secret="")


def test_encode_rejects_invalid_ttl() -> None:
    with pytest.raises(ShareTokenError):
        encode_share_token(42, secret=SECRET, ttl_hours=0)
    with pytest.raises(ShareTokenError):
        encode_share_token(42, secret=SECRET, ttl_hours=MAX_TTL_HOURS + 1)


def test_decode_with_empty_secret_raises() -> None:
    token = encode_share_token(42, secret=SECRET)
    with pytest.raises(ShareTokenError):
        decode_share_token(token, secret="")


def test_default_ttl_hours_24() -> None:
    assert DEFAULT_TTL_HOURS == 24


# --------------------------------------------------------------------------- #
# Endpoint testleri (reportlab gerekir)
# --------------------------------------------------------------------------- #


if not REPORTLAB_AVAILABLE:
    pytestmark = pytest.mark.skip(reason="reportlab kurulu değil")


@pytest.fixture
def session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as _Session
    from app.db.base import Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _Session(engine) as s:
        yield s


def _seed_output(session) -> int:
    from app.db import models
    now = datetime.now(UTC)
    row = models.AgentOutput(
        agent_name="pre_match_report",
        agent_version="1",
        subject_type="team",
        subject_id=11,
        output_json='{"wins": 4}',
        summary="özet",
        created_at=now, updated_at=now,
    )
    session.add(row)
    session.flush()
    return row.id


def _stub_settings(secret: str):
    """get_settings().jwt_secret_key mock."""
    class _S:
        jwt_secret_key = secret
    return _S()


def test_create_share_link_returns_token_and_url(session) -> None:
    from app.api.reports import create_share_link
    out_id = _seed_output(session)
    fake_request = type("R", (), {"base_url": "http://test/"})()
    with patch("app.api.reports.get_settings", return_value=_stub_settings(SECRET)):
        result = create_share_link(
            output_id=out_id, request=fake_request,
            ttl_hours=2, session=session,
        )
    assert result["output_id"] == out_id
    assert result["ttl_hours"] == 2
    assert result["url"].startswith("http://test/shared/reports/")
    assert "." in result["token"]


def test_create_share_link_503_without_secret(session) -> None:
    from fastapi import HTTPException
    from app.api.reports import create_share_link
    out_id = _seed_output(session)
    fake_request = type("R", (), {"base_url": "http://test/"})()
    with patch("app.api.reports.get_settings", return_value=_stub_settings("")):
        with pytest.raises(HTTPException) as exc:
            create_share_link(
                output_id=out_id, request=fake_request,
                ttl_hours=2, session=session,
            )
    assert exc.value.status_code == 503


def test_create_share_link_404_unknown(session) -> None:
    from fastapi import HTTPException
    from app.api.reports import create_share_link
    fake_request = type("R", (), {"base_url": "http://test/"})()
    with patch("app.api.reports.get_settings", return_value=_stub_settings(SECRET)):
        with pytest.raises(HTTPException) as exc:
            create_share_link(
                output_id=9999, request=fake_request,
                ttl_hours=2, session=session,
            )
    assert exc.value.status_code == 404


def test_shared_report_pdf_round_trip(session) -> None:
    from app.api.shared import shared_report_pdf
    out_id = _seed_output(session)
    token = encode_share_token(out_id, secret=SECRET)
    with patch("app.api.shared.get_settings", return_value=_stub_settings(SECRET)):
        resp = shared_report_pdf(token=token, session=session)
    assert resp.media_type == "application/pdf"
    assert resp.body.startswith(b"%PDF-")
    assert resp.headers["Cache-Control"] == "private, no-store"


def test_shared_report_pdf_403_tampered(session) -> None:
    from fastapi import HTTPException
    from app.api.shared import shared_report_pdf
    out_id = _seed_output(session)
    token = encode_share_token(out_id, secret=SECRET)
    bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with patch("app.api.shared.get_settings", return_value=_stub_settings(SECRET)):
        with pytest.raises(HTTPException) as exc:
            shared_report_pdf(token=bad, session=session)
    assert exc.value.status_code == 403


def test_shared_report_pdf_410_expired(session) -> None:
    from fastapi import HTTPException
    from app.api.shared import shared_report_pdf
    out_id = _seed_output(session)
    past = datetime.now(UTC) - timedelta(hours=2)
    token = encode_share_token(out_id, secret=SECRET, ttl_hours=1, now=past)
    with patch("app.api.shared.get_settings", return_value=_stub_settings(SECRET)):
        with pytest.raises(HTTPException) as exc:
            shared_report_pdf(token=token, session=session)
    assert exc.value.status_code == 410


def test_shared_report_pdf_503_without_secret(session) -> None:
    from fastapi import HTTPException
    from app.api.shared import shared_report_pdf
    with patch("app.api.shared.get_settings", return_value=_stub_settings("")):
        with pytest.raises(HTTPException) as exc:
            shared_report_pdf(token="x.y", session=session)
    assert exc.value.status_code == 503


def test_shared_report_pdf_404_after_output_deleted(session) -> None:
    from fastapi import HTTPException
    from app.api.shared import shared_report_pdf
    out_id = _seed_output(session)
    token = encode_share_token(out_id, secret=SECRET)
    # Output siliniyor — token hâlâ geçerli ama hedef yok
    from app.db import models
    session.query(models.AgentOutput).filter_by(id=out_id).delete()
    session.flush()
    with patch("app.api.shared.get_settings", return_value=_stub_settings(SECRET)):
        with pytest.raises(HTTPException) as exc:
            shared_report_pdf(token=token, session=session)
    assert exc.value.status_code == 404
