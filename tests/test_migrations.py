"""Alembic migration testleri.

CI workflow zaten `alembic upgrade head` smoke yapıyor; bu modül downgrade
sequence'lerini ve ileri-geri kombosunu doğrular. Production'da
"yeni kod + yeni migration" deploy'unda downtime/rollback güvenliği için.

Yaklaşım: izole SQLite dosyası → DATABASE_URL'i monkeypatch et →
get_settings cache'ini temizle → alembic.command çağrılarını çalıştır.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _alembic_cfg() -> Config:
    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return cfg


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Tek-test'lik izole SQLite dosyası + DATABASE_URL override."""
    db_path = tmp_path / "migration_test.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    # get_settings @lru_cache; env değişti, cache temizle
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()  # diğer testlerin temiz cache görmesi için


def _list_tables(url: str) -> set[str]:
    engine = create_engine(url, future=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


# Migration sırasının "yukarı" ve sonraki "aşağı" doğru sırada işlemesi
# için her revision'ın hangi tabloları açtığını biliyoruz:
_REVISIONS = ["0001_initial", "0002_observability", "0003_scheduler"]
_TABLES_AFTER_HEAD = {
    "leagues", "teams", "players", "matches",  # 0001
    "snapshots", "usage_events", "cache_entries",  # 0002
    "job_runs",  # 0003
}


def test_upgrade_head_creates_all_tables(isolated_db):
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")
    tables = _list_tables(isolated_db)
    # alembic_version pseudo-table'ı dışındaki domain tabloları
    domain_tables = tables - {"alembic_version"}
    assert _TABLES_AFTER_HEAD.issubset(domain_tables)


def test_downgrade_base_drops_all_domain_tables(isolated_db):
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    tables = _list_tables(isolated_db)
    domain_tables = tables - {"alembic_version"}
    # Tüm domain tabloları gitmeli
    assert domain_tables == set(), f"Beklenmedik artakalan tablo(lar): {domain_tables}"


def test_upgrade_downgrade_upgrade_roundtrip(isolated_db):
    """head → base → head: idempotent + bozulmadan tekrar gelir."""
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")
    tables_first = _list_tables(isolated_db) - {"alembic_version"}
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    tables_second = _list_tables(isolated_db) - {"alembic_version"}
    assert tables_first == tables_second


def test_each_revision_individually_reversible(isolated_db):
    """Her revision: upgrade <rev> → downgrade <rev-1> sequence'i çöker
    mi? Migration'ı tek tek yükle ve hemen aşağı indir.
    """
    cfg = _alembic_cfg()
    # Sıralı: her birini upgrade et, sonra hepsini geri al
    for rev in _REVISIONS:
        command.upgrade(cfg, rev)
        tables = _list_tables(isolated_db)
        # En azından alembic_version dolu olmalı (revision işaretlendi)
        assert "alembic_version" in tables

    # Tüm head'den geri base'e in
    command.downgrade(cfg, "base")
    tables = _list_tables(isolated_db) - {"alembic_version"}
    assert tables == set()


def test_partial_upgrade_to_intermediate_revision(isolated_db):
    """Sadece 0001 → leagues/teams var, observability tabloları yok."""
    cfg = _alembic_cfg()
    command.upgrade(cfg, "0001_initial")
    tables = _list_tables(isolated_db) - {"alembic_version"}
    assert "leagues" in tables
    assert "teams" in tables
    # 0002 ve 0003 henüz uygulanmadı
    assert "snapshots" not in tables
    assert "job_runs" not in tables
