"""Clip Assembler — video clip meta engine."""
from __future__ import annotations

import os

import pytest

from app.engine.clip_assembler import compute_clip_for_decision


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Her test başında CLIP_BASE_URL temiz."""
    monkeypatch.delenv("CLIP_BASE_URL", raising=False)
    yield


def test_stub_when_env_unset():
    r = compute_clip_for_decision(
        match_external_id=9300, minute=70.0,
    ).value
    assert r.available is False
    assert r.video_url is None
    assert r.source == "stub"
    assert r.clip_id.startswith("clip-9300-")


def test_url_when_env_set(monkeypatch):
    monkeypatch.setenv("CLIP_BASE_URL", "https://video.tactic11.com/clips")
    r = compute_clip_for_decision(
        match_external_id=9300, minute=70.0,
        decision_type="substitution", tenant_id="t-bjk",
    ).value
    assert r.available is True
    assert r.source == "broadcast"
    assert "t-bjk" in r.video_url
    assert "9300" in r.video_url
    # 70.0 * 60 = 4200 sn; back=20 (sub), forward=5 → 4180-4205
    assert r.start_second == 4180
    assert r.end_second == 4205
    assert r.duration_seconds == 25


def test_window_back_seconds_varies_by_decision_type():
    sub = compute_clip_for_decision(
        match_external_id=1, minute=60.0, decision_type="substitution",
    ).value
    tac = compute_clip_for_decision(
        match_external_id=1, minute=60.0, decision_type="tactical_instruction",
    ).value
    fc = compute_clip_for_decision(
        match_external_id=1, minute=60.0, decision_type="formation_change",
    ).value
    sp = compute_clip_for_decision(
        match_external_id=1, minute=60.0, decision_type="set_piece",
    ).value
    # set_piece en kısa, formation_change en uzun
    assert sp.duration_seconds < sub.duration_seconds < tac.duration_seconds < fc.duration_seconds


def test_deterministic_clip_id():
    """Aynı (match, minute, type) → aynı clip_id."""
    r1 = compute_clip_for_decision(
        match_external_id=9300, minute=72.5, decision_type="substitution",
    ).value
    r2 = compute_clip_for_decision(
        match_external_id=9300, minute=72.5, decision_type="substitution",
    ).value
    assert r1.clip_id == r2.clip_id


def test_minute_label_format():
    r = compute_clip_for_decision(
        match_external_id=1, minute=45.5,
    ).value
    assert r.poster_minute_label == "45' 30\""


def test_audit_complete():
    res = compute_clip_for_decision(
        match_external_id=9300, minute=70.0, decision_type="substitution",
    )
    a = res.audit.value
    assert "clip_id" in a
    assert "duration_seconds" in a
    assert "available" in a
    assert "label" in a


def test_back_seconds_override():
    r = compute_clip_for_decision(
        match_external_id=1, minute=60.0,
        decision_type="other", back_seconds=60, forward_seconds=10,
    ).value
    assert r.start_second == 60 * 60 - 60
    assert r.end_second == 60 * 60 + 10
    assert r.duration_seconds == 70


def test_negative_start_clamped_to_zero():
    """1. dakika - 30 sn = negatif → 0'a clamp."""
    r = compute_clip_for_decision(
        match_external_id=1, minute=0.5,  # 30 sn
    ).value
    assert r.start_second == 0


def test_env_cleanup_isolated_between_tests():
    """CLIP_BASE_URL bir testten diğerine sızmasın."""
    assert os.environ.get("CLIP_BASE_URL", "") == ""
    r = compute_clip_for_decision(
        match_external_id=1, minute=60.0,
    ).value
    assert r.available is False
