"""Maç sesli not sayfa render testleri (Faz 5 #20)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.api.html_views import match_voice_notes_view


def test_voice_notes_returns_html() -> None:
    resp = match_voice_notes_view(match_id=9100)
    assert isinstance(resp, HTMLResponse)
    body = resp.body.decode("utf-8")
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert "window.MATCH_ID = 9100;" in body
    assert "Sesli Not" in body


def test_voice_notes_rejects_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc:
        match_voice_notes_view(match_id=0)
    assert exc.value.status_code == 400


def test_voice_notes_has_media_recorder_api() -> None:
    """MediaRecorder + getUserMedia çağrıları var."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "MediaRecorder" in body
    assert "navigator.mediaDevices" in body
    assert "getUserMedia" in body


def test_voice_notes_has_six_quick_tags() -> None:
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    expected_tags = [
        "substitution", "formation", "opponent",
        "tactical", "injury", "other",
    ]
    for tag in expected_tags:
        assert f'data-tag="{tag}"' in body


def test_voice_notes_keyboard_shortcuts() -> None:
    """Boşluk + Esc + tek harf kısayolları var."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "e.code === 'Space'" in body
    assert "e.code === 'Escape'" in body
    assert "data-key=" in body


def test_voice_notes_localstorage_per_match() -> None:
    """Notlar maç başına izole localStorage anahtarında."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "manager2_voice_notes_" in body
    # Anahtar match_id'yi içermeli
    assert "STORAGE = 'manager2_voice_notes_' + MATCH_ID" in body


def test_voice_notes_export_json() -> None:
    """JSON dışa aktar butonu — Blob + download link."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "export" in body
    assert "JSON dışa aktar" in body
    assert "voice_notes_match_" in body  # Filename pattern


def test_voice_notes_permissions_warning_block() -> None:
    """Mikrofon izni reddedilirse uyarı div'i var."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "perms-warn" in body
    assert "izni reddedildi" in body or "permission" in body.lower()


def test_voice_notes_deep_link_to_live() -> None:
    """Canlı sayfa derin linki var."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    assert "live-link" in body
    assert "/live" in body


def test_voice_notes_tag_colors_unique() -> None:
    """6 tag farklı CSS class'a sahip — görsel ayrım."""
    resp = match_voice_notes_view(match_id=42)
    body = resp.body.decode("utf-8")
    for tag_class in [
        ".tag-substitution", ".tag-formation", ".tag-opponent",
        ".tag-tactical", ".tag-injury", ".tag-other",
    ]:
        assert tag_class in body
