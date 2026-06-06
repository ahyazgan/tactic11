"""Dev veri garantisi — demo.db'de bir gerçek maç var mı, yoksa indir.

Idempotent: maç zaten varsa ağa çıkmaz, hiçbir şey yapmaz. İlk çalıştırmada
(boş DB) StatsBomb'dan Barcelona–Sevilla maçını t-default tenant'ı altına ingest
eder. `dev_api.py` uvicorn'dan önce bunu çağırır → "npm run dev" ile her şey hazır.
"""
from __future__ import annotations

DEMO_MATCH_ID = 16029
DEMO_TENANT = "t-default"


def ensure_demo_data(match_id: int = DEMO_MATCH_ID, tenant: str = DEMO_TENANT) -> str:
    """Maç + event'ler `tenant` altında var mı garanti et. Durum string'i döner."""
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.db import models

    Base.metadata.create_all(engine)

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

    if match_row is not None and event_count is not None:
        return f"hazır (match {match_id} / {tenant} mevcut)"

    # Eksik → StatsBomb'dan indir (ağ gerekir, tek seferlik).
    from scripts.demo_real_statsbomb import run_demo
    run_demo(match_id=match_id, tenant_id=tenant)
    return f"indirildi (match {match_id} / {tenant})"


if __name__ == "__main__":
    print(ensure_demo_data())
