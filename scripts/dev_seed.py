"""Dev veri garantisi — demo.db'de bir gerçek maç var mı, yoksa indir.

Idempotent: maç zaten varsa ağa çıkmaz, hiçbir şey yapmaz. İlk çalıştırmada
(boş DB) StatsBomb'dan Barcelona–Sevilla maçını t-default tenant'ı altına ingest
eder. `dev_api.py` uvicorn'dan önce bunu çağırır → "npm run dev" ile her şey hazır.
"""
from __future__ import annotations

DEMO_MATCH_ID = 16029
DEMO_TENANT = "t-default"


def _sync_missing_columns(engine) -> list[str]:
    """Dev sqlite şema senkronu — modelde olup DB'de olmayan kolonları ekle.

    create_all yeni TABLO açar ama mevcut tabloya kolon EKLEMEZ; eski demo.db +
    yeni migration kolonu = açılışta OperationalError (yaşandı: 0027'nin 9
    appearance kolonu). Bu yardımcı yalnız EKLEME yapar (veri kaybı yok);
    NOT NULL kolonlar sabit default'uyla, yoksa nullable eklenir. Prod'da
    alembic kullanılır — bu sadece dev kolaylığı."""
    from sqlalchemy import inspect, text

    from app.db.base import Base

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # yeni tabloyu create_all halleder
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = (
                    f"ALTER TABLE {table.name} ADD COLUMN "
                    f"{col.name} {col.type.compile(engine.dialect)}"
                )
                if not col.nullable:
                    default = getattr(col.default, "arg", None)
                    if isinstance(default, bool):
                        ddl += f" NOT NULL DEFAULT {int(default)}"
                    elif isinstance(default, (int, float)):
                        ddl += f" NOT NULL DEFAULT {default}"
                    elif isinstance(default, str):
                        ddl += f" NOT NULL DEFAULT '{default}'"
                    # sabit default'suz NOT NULL sqlite'a eklenemez → nullable kalır
                conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
    return added


def ensure_demo_data(match_id: int = DEMO_MATCH_ID, tenant: str = DEMO_TENANT) -> str:
    """Maç + event'ler `tenant` altında var mı garanti et. Durum string'i döner."""
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.db import models

    Base.metadata.create_all(engine)
    synced = _sync_missing_columns(engine)
    if synced:
        print(f"[dev_seed] şema senkron: {len(synced)} kolon eklendi → {', '.join(synced)}")

    with SessionLocal() as s:
        match_row = s.execute(
            models.Match.__table__.select().where(
                models.Match.external_id == match_id,
                models.Match.tenant_id == tenant,
            )
        ).first()
        event_count = s.execute(
            models.EventRow.__table__.select().where(
                models.EventRow.match_external_id == match_id,
                models.EventRow.tenant_id == tenant,
            ).limit(1)
        ).first()
        appearance_count = s.execute(
            models.PlayerAppearance.__table__.select().where(
                models.PlayerAppearance.match_external_id == match_id,
                models.PlayerAppearance.tenant_id == tenant,
            ).limit(1)
        ).first()

    if match_row is not None and event_count is not None:
        # Maç + event hazır; Faz B kadro verisi eksikse onu backfill et (tek ağ).
        if appearance_count is None:
            status = _backfill_appearances(match_id, tenant)
            return f"hazır (match {match_id} / {tenant}) + {status}"
        return f"hazır (match {match_id} / {tenant} mevcut)"

    # Eksik → StatsBomb'dan indir (ağ gerekir, tek seferlik).
    from scripts.demo_real_statsbomb import run_demo
    run_demo(match_id=match_id, tenant_id=tenant)
    return f"indirildi (match {match_id} / {tenant})"


def _backfill_appearances(match_id: int, tenant: str) -> str:
    """Maç+event var ama kadro (appearance) yok → sadece appearance'ı doldur."""
    from app.data.sources.statsbomb_open import StatsBombOpen
    from app.db import models
    from app.db.session import SessionLocal
    from scripts.demo_real_statsbomb import _ingest_appearances

    with SessionLocal() as s:
        s.info["tenant_id"] = tenant
        match = s.execute(
            models.Match.__table__.select().where(
                models.Match.external_id == match_id,
                models.Match.tenant_id == tenant,
            )
        ).one()
        n = _ingest_appearances(
            s, StatsBombOpen(), match_id=match_id, tenant_id=tenant,
            kickoff=match.kickoff,
        )
        s.commit()
    return f"kadro backfill ({n} appearance)"


if __name__ == "__main__":
    print(ensure_demo_data())
