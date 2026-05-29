"""StatsBomb 360 adapter testleri (Faz 5 #45)."""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.data.sources.statsbomb_360 import (
    AWAY_PLAYER_BASE_ID,
    DEFAULT_API_BASE,
    HOME_PLAYER_BASE_ID,
    SB_PITCH_X,
    SB_PITCH_Y,
    StatsBomb360Adapter,
    StatsBomb360Error,
)


# --------------------------------------------------------------------------- #
# Saf yardımcılar
# --------------------------------------------------------------------------- #


def test_normalize_xy_center() -> None:
    x, y = StatsBomb360Adapter._normalize_xy([60.0, 40.0])
    # Pitch merkezi 120/2, 80/2 → 50, 50
    assert x == 50.0
    assert y == 50.0


def test_normalize_xy_corner_top_right() -> None:
    x, y = StatsBomb360Adapter._normalize_xy([SB_PITCH_X, SB_PITCH_Y])
    assert x == 100.0
    assert y == 100.0


def test_normalize_xy_clamp_negative() -> None:
    x, y = StatsBomb360Adapter._normalize_xy([-5.0, -5.0])
    assert x == 0.0
    assert y == 0.0


def test_normalize_xy_clamp_above_pitch() -> None:
    x, y = StatsBomb360Adapter._normalize_xy([200.0, 200.0])
    assert x == 100.0
    assert y == 100.0


def test_normalize_xy_empty_returns_center() -> None:
    """Boş location → fallback (50, 50)."""
    x, y = StatsBomb360Adapter._normalize_xy([])
    assert x == 50.0
    assert y == 50.0


def test_convert_entry_teammate_uses_home_base() -> None:
    entry = {"teammate": True, "location": [60.0, 40.0]}
    pos = StatsBomb360Adapter._convert_entry(entry, index=3)
    assert pos is not None
    assert pos.player_external_id == HOME_PLAYER_BASE_ID + 3


def test_convert_entry_opponent_uses_away_base() -> None:
    entry = {"teammate": False, "location": [60.0, 40.0]}
    pos = StatsBomb360Adapter._convert_entry(entry, index=5)
    assert pos is not None
    assert pos.player_external_id == AWAY_PLAYER_BASE_ID + 5


def test_convert_entry_no_location_returns_none() -> None:
    entry = {"teammate": True}
    assert StatsBomb360Adapter._convert_entry(entry, 0) is None


# --------------------------------------------------------------------------- #
# Mock HTTP client + end-to-end iteration
# --------------------------------------------------------------------------- #


class _FakeResp:
    def __init__(self, status_code: int, payload: Any, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.last_url: str | None = None

    def get(self, url: str, timeout: float | None = None) -> _FakeResp:
        self.last_url = url
        return self._resp


def _sample_360_payload() -> list[dict[str, Any]]:
    return [
        {
            "event_uuid": "e1",
            "freeze_frame": [
                {"teammate": True, "location": [60.0, 40.0]},
                {"teammate": False, "location": [80.0, 30.0]},
            ],
        },
        {
            "event_uuid": "e2",
            "freeze_frame": [
                {"teammate": True, "location": [30.0, 20.0]},
            ],
        },
        # Event with no freeze frame — atlanmalı
        {"event_uuid": "e3", "freeze_frame": []},
    ]


def test_get_match_frames_produces_frames_per_event() -> None:
    client = _FakeClient(_FakeResp(200, _sample_360_payload()))
    adapter = StatsBomb360Adapter(http_client=client)
    frames = list(adapter.get_match_frames(match_external_id=9100))
    # 3. event freeze_frame boş → atlanır; toplam 2 frame
    assert len(frames) == 2
    f1 = frames[0]
    assert f1.match_external_id == 9100
    assert f1.sport == "football"
    assert len(f1.players) == 2
    # İlk player teammate → home base
    assert f1.players[0].player_external_id == HOME_PLAYER_BASE_ID
    assert f1.players[1].player_external_id == AWAY_PLAYER_BASE_ID + 1
    assert client.last_url.endswith("/9100.json")


def test_fetch_404_raises_with_match_id_in_message() -> None:
    client = _FakeClient(_FakeResp(404, "Not Found"))
    adapter = StatsBomb360Adapter(http_client=client)
    with pytest.raises(StatsBomb360Error) as exc:
        list(adapter.get_match_frames(match_external_id=9999))
    assert "9999" in str(exc.value)
    assert "404" in str(exc.value)


def test_fetch_5xx_raises() -> None:
    client = _FakeClient(_FakeResp(500, "boom", text="server error"))
    adapter = StatsBomb360Adapter(http_client=client)
    with pytest.raises(StatsBomb360Error) as exc:
        list(adapter.get_match_frames(match_external_id=1))
    assert "500" in str(exc.value)


def test_fetch_non_list_payload_raises() -> None:
    client = _FakeClient(_FakeResp(200, {"oops": "dict not list"}))
    adapter = StatsBomb360Adapter(http_client=client)
    with pytest.raises(StatsBomb360Error) as exc:
        list(adapter.get_match_frames(match_external_id=1))
    assert "list" in str(exc.value)


def test_fetch_invalid_json_raises() -> None:
    client = _FakeClient(_FakeResp(200, ValueError("bad json")))
    adapter = StatsBomb360Adapter(http_client=client)
    with pytest.raises(StatsBomb360Error) as exc:
        list(adapter.get_match_frames(match_external_id=1))
    assert "JSON parse" in str(exc.value)


def test_fetch_network_error_raises() -> None:
    class _NetClient:
        def get(self, url: str, timeout: float | None = None) -> _FakeResp:
            raise httpx.ConnectError("dns fail")

    adapter = StatsBomb360Adapter(http_client=_NetClient())  # type: ignore[arg-type]
    with pytest.raises(StatsBomb360Error) as exc:
        list(adapter.get_match_frames(match_external_id=1))
    assert "HTTP error" in str(exc.value)


def test_default_api_base_uses_statsbomb_open_data() -> None:
    assert "statsbomb/open-data" in DEFAULT_API_BASE
    assert "three-sixty" in DEFAULT_API_BASE


def test_adapter_is_tracking_data_source_subclass() -> None:
    """ABC sözleşmesine uyuyor — Liskov substitution doğrulaması."""
    from app.data.sources.tracking import TrackingDataSource
    assert issubclass(StatsBomb360Adapter, TrackingDataSource)


def test_get_match_frames_skips_non_dict_events() -> None:
    payload = [
        {"freeze_frame": [{"teammate": True, "location": [60, 40]}]},
        "not-a-dict",
        None,
    ]
    client = _FakeClient(_FakeResp(200, payload))
    adapter = StatsBomb360Adapter(http_client=client)
    frames = list(adapter.get_match_frames(match_external_id=1))
    assert len(frames) == 1  # sadece ilk geçerli
