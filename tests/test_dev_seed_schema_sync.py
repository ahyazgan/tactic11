"""dev_seed._sync_missing_columns — eski demo.db'ye yeni model kolonu ekleme.

Gerçek vaka: migration 0027'nin 9 appearance kolonu eski demo.db'de yoktu →
backend açılışta OperationalError. Senkron yalnız EKLER (veri kaybı yok),
idempotenttir.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db import models  # noqa: F401 — tabloları metadata'ya kaydet
from app.db.base import Base
from scripts.dev_seed import _sync_missing_columns


def test_sync_adds_dropped_columns_and_is_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)

    # Eski-DB simülasyonu: iki nullable kolonu düşür (sqlite 3.35+ DROP COLUMN).
    with eng.begin() as c:
        c.execute(text("ALTER TABLE player_appearances DROP COLUMN goals"))
        c.execute(text("ALTER TABLE player_appearances DROP COLUMN saves"))

    added = _sync_missing_columns(eng)
    assert "player_appearances.goals" in added
    assert "player_appearances.saves" in added

    cols = {col["name"] for col in inspect(eng).get_columns("player_appearances")}
    assert "goals" in cols and "saves" in cols

    # İkinci koşu hiçbir şey eklemez (idempotent).
    assert _sync_missing_columns(eng) == []


def test_sync_noop_on_fresh_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(eng)
    assert _sync_missing_columns(eng) == []
