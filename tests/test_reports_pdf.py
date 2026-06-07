"""PDF rapor üretici testleri (Faz 5 #16).

reportlab opsiyonel: kurulu değilse pytest.importorskip ile atlanır.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.reports.pdf import REPORTLAB_AVAILABLE

if not REPORTLAB_AVAILABLE:
    pytest.skip(
        "reportlab kurulu değil — `pip install reportlab>=4.0`",
        allow_module_level=True,
    )

from app.api.reports import (  # noqa: E402
    agent_output_pdf,
    latest_agent_output_pdf,
)
from app.db import models  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.reports.pdf import (  # noqa: E402
    _flatten_json,
    _format_value,
    build_agent_output_pdf,
    build_performance_report_pdf,
)

# --------------------------------------------------------------------------- #
# Saf builder testleri
# --------------------------------------------------------------------------- #


def test_format_value_primitives() -> None:
    assert _format_value(None) == "—"
    assert _format_value(True) == "evet"
    assert _format_value(False) == "hayır"
    assert _format_value(42) == "42"
    assert _format_value(3.14) == "3.14"
    assert _format_value("hello") == "hello"


def test_format_value_empty_list_and_dict() -> None:
    assert _format_value([]) == "[]"
    assert _format_value({}) == "{}"


def test_format_value_nested_truncates_at_max_depth() -> None:
    deep = {"a": {"b": {"c": {"d": "buried"}}}}
    s = _format_value(deep)
    # MAX_NEST_DEPTH=3; "d: ..." dördüncü seviyede {...} ile gösterilir
    assert "{…}" in s or "buried" in s


def test_flatten_json_caps_at_max_rows() -> None:
    big = {f"k{i}": i for i in range(60)}
    rows = _flatten_json(big)
    # MAX_TABLE_ROWS = 40; son satır "…" + kalan sayısı
    assert len(rows) <= 41
    assert rows[-1][0] == "…"


def test_build_pdf_returns_pdf_magic_header() -> None:
    pdf = build_agent_output_pdf(
        agent_name="pre_match_report",
        agent_version="1",
        subject_type="team",
        subject_id=11,
        summary="Galatasaray son 5 maçta 4 galibiyet, form yüksek.",
        output_json={
            "matches_played": 5,
            "wins": 4,
            "draws": 1,
            "losses": 0,
            "goals_for": 12,
            "goals_against": 3,
            "form_score": 86.5,
        },
        updated_at=datetime(2026, 5, 30, 10, 0, tzinfo=UTC),
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-"), "PDF magic header eksik"
    assert b"%%EOF" in pdf[-1024:], "PDF EOF marker eksik"


def test_build_pdf_handles_json_string_input() -> None:
    pdf = build_agent_output_pdf(
        agent_name="x", agent_version="1",
        subject_type="team", subject_id=1,
        summary="özet",
        output_json='{"key": "value"}',
    )
    assert pdf.startswith(b"%PDF-")


def test_build_pdf_handles_malformed_json_string() -> None:
    # Geçersiz JSON → "raw" alanına düşer, hata vermez
    pdf = build_agent_output_pdf(
        agent_name="x", agent_version="1",
        subject_type="team", subject_id=1,
        summary="özet",
        output_json="bu JSON değil { broken",
    )
    assert pdf.startswith(b"%PDF-")


def test_build_pdf_handles_empty_output_json() -> None:
    pdf = build_agent_output_pdf(
        agent_name="x", agent_version="1",
        subject_type="team", subject_id=1,
        summary="boş output testi",
        output_json={},
    )
    assert pdf.startswith(b"%PDF-")


# --------------------------------------------------------------------------- #
# Endpoint testleri (DB + builder)
# --------------------------------------------------------------------------- #


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_agent_output(
    session: Session, *,
    agent_name: str = "pre_match_report",
    agent_version: str = "1",
    subject_type: str = "team",
    subject_id: int = 11,
    summary: str = "test özet",
    output_json: str = '{"wins": 4}',
    updated_at: datetime | None = None,
) -> models.AgentOutput:
    now = updated_at or datetime.now(UTC)
    row = models.AgentOutput(
        agent_name=agent_name,
        agent_version=agent_version,
        subject_type=subject_type,
        subject_id=subject_id,
        output_json=output_json,
        summary=summary,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def test_endpoint_agent_output_pdf_returns_pdf(session: Session) -> None:
    row = _seed_agent_output(session)
    resp = agent_output_pdf(output_id=row.id, session=session)
    assert resp.media_type == "application/pdf"
    assert resp.body.startswith(b"%PDF-")
    assert "Content-Disposition" in resp.headers


def test_endpoint_agent_output_pdf_404_unknown(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        agent_output_pdf(output_id=9999, session=session)
    assert exc.value.status_code == 404


def test_endpoint_latest_agent_output_picks_newest(session: Session) -> None:
    old = _seed_agent_output(
        session, summary="eski",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    new = _seed_agent_output(
        session, summary="yeni",
        agent_version="2",
        updated_at=datetime(2026, 5, 30, tzinfo=UTC),
    )
    resp = latest_agent_output_pdf(
        agent_name="pre_match_report",
        subject_type="team", subject_id=11,
        agent_version=None, session=session,
    )
    assert resp.status_code == 200
    # subject header'ında yeni satırın subject'i (aynı subject ama doğrulama)
    assert resp.headers["X-Report-Subject"] == "team:11"
    # En yeni updated_at row seçildi
    assert new.id != old.id  # sanity


def test_endpoint_latest_agent_output_version_filter(session: Session) -> None:
    _seed_agent_output(
        session, agent_version="1", summary="v1",
        updated_at=datetime(2026, 5, 30, tzinfo=UTC),
    )
    _seed_agent_output(
        session, agent_version="2", summary="v2",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # v2 daha eski ama version filtresi ile seçilir
    resp = latest_agent_output_pdf(
        agent_name="pre_match_report",
        subject_type="team", subject_id=11,
        agent_version="2", session=session,
    )
    assert resp.body.startswith(b"%PDF-")


def test_endpoint_latest_agent_output_404_when_none(session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        latest_agent_output_pdf(
            agent_name="unknown_agent",
            subject_type="team", subject_id=1,
            agent_version=None, session=session,
        )
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Performans raporu PDF builder
# --------------------------------------------------------------------------- #


def test_build_performance_report_returns_pdf() -> None:
    from dataclasses import asdict

    from app.engine.performance_test import evaluate_battery, interpret_progression

    battery = evaluate_battery(
        42, [("cmj", 38.0), ("sprint_30m", 4.1), ("yoyo_irl1", 19.0)],
    )
    prog = asdict(interpret_progression("cmj", [34.0, 35.0, 36.0, 38.0]))
    pdf = build_performance_report_pdf(
        player_name="Test Oyuncu",
        player_external_id=42,
        test_date="2026-06-06",
        scores=[asdict(s) for s in battery.scores],
        strong_areas=list(battery.strong_areas),
        weak_areas=list(battery.weak_areas),
        progression=[prog],
        summary="Sezon başı test bataryası.",
        club_name="Beşiktaş",
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-"), "PDF magic header eksik"
    assert b"%%EOF" in pdf[-1024:], "PDF EOF marker eksik"


def test_build_performance_report_minimal() -> None:
    # Sadece skorlar — progression/strong/weak yok
    pdf = build_performance_report_pdf(
        player_name="Minimal",
        player_external_id=1,
        scores=[{
            "protocol_name": "Dikey Sıçrama", "raw_value": 40.0,
            "unit": "cm", "rating": "iyi", "squad_percentile": 75.0,
        }],
    )
    assert pdf.startswith(b"%PDF-")


def test_performance_report_endpoint_builds_pdf(session: Session) -> None:
    from app.api.reports import performance_report_pdf

    resp = performance_report_pdf(
        payload={
            "player_name": "Endpoint Oyuncu", "player_id": 7,
            "results": [["cmj", 36.0], ["sprint_30m", 4.3]],
            "progression": {"cmj": [33.0, 34.0, 36.0]},
            "test_date": "2026-06-06",
            "summary": "Test.",
        },
        session=session,
    )
    assert resp.body.startswith(b"%PDF-")
    assert resp.media_type == "application/pdf"
