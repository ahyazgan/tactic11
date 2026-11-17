"""Maç raporu: dilimler, güvenilirlik, özet ve sapma bulguları."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain import PlayerPosition, TrackingFrame
from app.engine.tracking.match_report import MIN_SLICE_FRAMES, build_match_report
from tests.test_api_tracking import _seed, client  # noqa: F401  (pytest fixture)

HOME, AWAY = 11, 22


def _team(team: int, x0: float, half_width: float, n: int = 10) -> list[PlayerPosition]:
    """n oyuncu: iki sıra, y'de merkezden +-half_width metreye yayılmış."""
    out = []
    for i in range(n):
        y_m = 34.0 - half_width + 2 * half_width * (i % 5) / 4
        x_m = x0 + 10.0 * (i // 5)
        out.append(PlayerPosition(player_external_id=team * 100 + i, x=x_m / 105 * 100, y=y_m / 68 * 100,
                                  team_external_id=team, identity_estimated=True))
    return out


def _frames(minute0: float, count: int, half_width: float, n: int = 10, ball: bool = False) -> list[TrackingFrame]:
    base = datetime(2000, 1, 1, tzinfo=UTC)
    return [
        TrackingFrame(
            sport="football", match_external_id=1, timestamp=base + timedelta(minutes=minute0, seconds=i),
            period=1, minute=minute0 + i / 60, source="video_tracking",
            players=tuple(_team(HOME, 20.0, half_width, n) + _team(AWAY, 60.0, 20.0, n)),
            ball=PlayerPosition(player_external_id=0, x=20.0 / 105 * 100, y=50.0) if ball else None,
            possession_team_external_id=HOME if ball else None,
        )
        for i in range(count)
    ]


def test_summary_is_frame_weighted_over_reliable_slices_only():
    slices = [(0.0, 15.0, _frames(0, 60, 20.0)), (15.0, 30.0, _frames(15, 30, 26.0)),
              (30.0, 45.0, _frames(30, MIN_SLICE_FRAMES - 1, 5.0)), (45.0, 60.0, _frames(45, 60, 5.0, n=6))]
    report = build_match_report(HOME, AWAY, slices)
    home = [s["home"] for s in report["slices"]]
    assert [h["reliable"] for h in home] == [True, True, False, False]
    assert report["teams"]["home"]["summary"]["width_m"] == round((40.0 * 60 + 52.0 * 30) / 90, 1)
    assert report["teams"]["home"]["summary"]["reliable_slices"] == 2
    assert report["teams"]["home"]["summary"]["press_index"] is None


def test_findings_flag_slices_that_leave_the_match_mean():
    slices = [(15.0 * k, 15.0 * k + 15, _frames(15 * k, 60, 24.0 if k == 4 else 20.0)) for k in range(5)]
    findings = build_match_report(HOME, AWAY, slices)["findings"]
    widths = [f for f in findings if f["metric"] == "width_m"]
    assert [(f["side"], f["from_minute"], f["text"]) for f in widths] == [("home", 60.0, "genişledi")]
    assert widths[0]["delta"] == round(48.0 - (40 * 4 + 48) / 5, 1)
    assert not [f for f in findings if f["side"] == "away"]


def test_press_is_reported_only_with_enough_ball_frames():
    report = build_match_report(HOME, AWAY, [(0.0, 15.0, _frames(0, 60, 20.0, ball=True))])
    away = report["slices"][0]["away"]
    assert away["press_frames"] == 60 and away["press_index"] is not None
    assert report["slices"][0]["home"]["press_index"] is None
    assert report["teams"]["away"]["summary"]["press_index"] == away["press_index"]


def test_formation_is_withheld_unless_most_frames_agree():
    steady = build_match_report(HOME, AWAY, [(0.0, 15.0, _frames(0, 60, 20.0))])["slices"][0]["home"]
    assert steady["formation"] == "5-5" and steady["formation_support"] == 1.0
    mixed = _frames(0, 20, 20.0) + _frames(1, 20, 20.0, n=9) + _frames(2, 20, 20.0, n=8)
    shaky = build_match_report(HOME, AWAY, [(0.0, 15.0, mixed)])["slices"][0]["home"]
    assert shaky["formation"] is None and 0 < shaky["formation_support"] < 0.5


def test_no_reliable_slice_gives_no_summary_and_no_findings():
    report = build_match_report(HOME, AWAY, [(0.0, 15.0, _frames(0, 5, 20.0))])
    assert report["teams"]["home"]["summary"] is None and report["findings"] == []
    assert report["limits"]


def test_report_endpoint_slices_the_whole_match(session, client):  # noqa: F811
    _seed(session, frames=3)
    body = client.get("/tracking/matches/9600/report?slice_minutes=15").json()
    assert [(s["from_minute"], s["frames"]) for s in body["slices"]] == [(0.0, 1), (15.0, 1), (30.0, 1)]
    assert body["teams"]["home"]["team_external_id"] == 217 and body["teams"]["home"]["summary"] is None
    assert client.get("/tracking/matches/424242/report").status_code == 404


def test_report_pdf_renders_the_same_report_with_turkish_text(session, client):  # noqa: F811
    _seed(session, frames=3)
    r = client.get("/tracking/matches/9600/report.pdf?slice_minutes=15&our_side=away")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and b"BitstreamVera" in r.content
    assert 'filename="mac_raporu_9600.pdf"' in r.headers["content-disposition"]
    assert client.get("/tracking/matches/424242/report.pdf").status_code == 404


def test_pdf_builder_names_sides_and_keeps_limits():
    from app.reports.tracking_match_pdf import build_tracking_match_pdf

    report = build_match_report(217, 213, [(0.0, 15.0, _frames(0.0, 40, 10.0)), (15.0, 30.0, _frames(15.0, 40, 16.0))])
    report.update(match_id=1, slice_minutes=15.0, physical={"teams": {"home": None, "away": None}, "slices": [], "limits": ["fiziksel sınır"]})
    pdf = build_tracking_match_pdf(report, our_side="home", title="Beşiktaş – Antalyaspor", generated_at="2026-11-18")
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000


def test_pdf_title_uses_team_names_and_kickoff_date(session):
    from app.api.tracking import _report_title
    from app.db import models

    _seed(session, frames=1)
    session.add(models.Team(sport="football", external_id=217, name="Beşiktaş", tenant_id="t-default"))
    session.commit()
    title = _report_title(session, 9600)
    assert title.startswith("Beşiktaş – Takım 213 · ") and title[-10:].count(".") == 2
