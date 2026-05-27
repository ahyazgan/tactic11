"""Cursor-based pagination helper.

Admin endpoint'leri için "next page" cursor'u. Mevcut endpoint'ler `limit`
döner ama 200 satırdan fazla görmek için stable cursor lazım.

Cursor: base64(json([sort_value_iso, id])). Decode edip WHERE clause'a
çevirir: `(sort_field, id) < (cursor.sort_value, cursor.id)` (tuple
comparison desc sıra için).

Tuple comparison: "datetime aynıysa id'ye fall-back" semantic'i otomatik
sağlar — ilgili (created_at, id) çiftleri unique ve order-stable.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Cursor:
    """Sort key (ISO datetime) + tie-breaker id."""
    sort_value: str  # ISO datetime
    row_id: int

    def encode(self) -> str:
        payload = json.dumps([self.sort_value, self.row_id], separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> Cursor | None:
    """Base64 url-safe → Cursor. Geçersizse None döner (caller 400 fırlatabilir)."""
    if not cursor:
        return None
    try:
        # rstrip("=") ile encode ediyoruz; decode için padding gerek
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, list) or len(data) != 2:
            return None
        sort_value, row_id = data
        if not isinstance(sort_value, str) or not isinstance(row_id, int):
            return None
        # datetime parse — geçersiz format zatensa exception
        datetime.fromisoformat(sort_value)
        return Cursor(sort_value=sort_value, row_id=row_id)
    except (binascii.Error, ValueError, json.JSONDecodeError):
        return None


def build_next_cursor(rows: list, sort_attr: str, id_attr: str = "id") -> str | None:
    """Son satırdan next_cursor üret (yoksa None — sayfa sonu).

    `rows[-1]` zaten en eski (desc order); sonraki sayfa bu noktadan başlar.
    """
    if not rows:
        return None
    last = rows[-1]
    sort_val = getattr(last, sort_attr)
    row_id = getattr(last, id_attr)
    sort_val_str = sort_val.isoformat() if isinstance(sort_val, datetime) else str(sort_val)
    return Cursor(sort_value=sort_val_str, row_id=int(row_id)).encode()
