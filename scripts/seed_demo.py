"""Demo seed — fiziksel test paneli için örnek kadro + testler.

Beşiktaş sunumu gibi demolar için: panel boş açılmasın, çeşitli risk
seviyeleri (Düşük → Kritik) hazır gelsin.

Kullanım (kendi makinende; sandbox'ta runtime/ağ yok):
    export DATABASE_URL="sqlite:///./_demo.db"   # veya gerçek Postgres
    alembic upgrade head
    python -m scripts.seed_demo
    # admin@besiktas-demo / demo-password-1234 ile giriş → /physical-tests

NOT: idempotent değil — tekrar çalıştırınca aynı oyunculara yeni test ekler.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.auth.service import UserExists, create_user
from app.db import models
from app.db.physical_test import PhysicalTest
from app.db.session import SessionLocal

TENANT_ID = "besiktas-demo"
TENANT_SLUG = "besiktas"
ADMIN_EMAIL = "admin@besiktas-demo"
ADMIN_PASSWORD = "demo-password-1234"
TEST_DATE = date(2026, 6, 6)

# (player_id, ad, [(protokol, değer), ...]) — değerler load_risk REFERENCE'ına
# göre kasıtlı: kimi referans altı (riskli), kimi sağlıklı.
DEMO_PLAYERS: list[tuple[str, str, list[tuple[str, float]]]] = [
    # Kritik — birçok parametre referans dışı
    ("1001", "Rafa Silva", [
        ("sprint_10m", 2.05), ("cmj", 25.0), ("yoyo_irl1", 13.5), ("vo2max", 45.0),
    ]),
    # Düşük — sağlıklı
    ("1002", "Tammy Abraham", [
        ("sprint_10m", 1.79), ("cmj", 38.0), ("yoyo_irl1", 17.1),
    ]),
    # Orta/Yüksek — karışık
    ("1003", "Felix Uduokhai", [
        ("sprint_30m", 4.35), ("isokinetic_quad", 2.4), ("vo2max", 51.0),
    ]),
    # Düşük — elit değerler
    ("1004", "Semih Kılıçsoy", [
        ("sprint_10m", 1.74), ("yoyo_irl1", 18.4), ("cmj", 41.0), ("body_fat_pct", 9.2),
    ]),
]

_UNIT = {
    "sprint_10m": "sn", "sprint_30m": "sn", "yoyo_irl1": "seviye", "cmj": "cm",
    "isokinetic_quad": "Nm/kg", "isokinetic_ham": "Nm/kg", "vo2max": "ml/kg/min",
    "gps_total_dist": "m", "body_fat_pct": "%",
}


def _ensure_tenant(session) -> models.Tenant:
    tenant = session.get(models.Tenant, TENANT_ID)
    if tenant is not None:
        return tenant
    tenant = models.Tenant(
        id=TENANT_ID, slug=TENANT_SLUG, name="Beşiktaş (demo)",
        settings_json=json.dumps({}), active=True, created_at=datetime.now(UTC),
    )
    session.add(tenant)
    session.flush()
    return tenant


def _ensure_admin(session) -> None:
    try:
        create_user(
            session, tenant_id=TENANT_ID, email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD, role="admin",
        )
        print(f"  admin oluşturuldu: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    except UserExists:
        print(f"  admin zaten var: {ADMIN_EMAIL}")


def seed() -> int:
    inserted = 0
    with SessionLocal() as session:
        _ensure_tenant(session)
        _ensure_admin(session)
        for player_id, name, tests in DEMO_PLAYERS:
            for protocol, value in tests:
                session.add(PhysicalTest(
                    tenant_id=TENANT_ID, player_id=player_id, player_name=name,
                    test_date=TEST_DATE, protocol=protocol, value=value,
                    unit=_UNIT.get(protocol, ""), recorded_by="Demo Seed",
                ))
                inserted += 1
            print(f"  {name} (#{player_id}): {len(tests)} test")
        session.commit()
    return inserted


def main() -> int:
    print(f"Demo seed → tenant={TENANT_ID}")
    n = seed()
    print(f"Tamam: {n} test eklendi. /physical-tests panelinde görünür.")
    # Doğrulama: kayıtlar yazıldı mı?
    with SessionLocal() as session:
        count = len(session.execute(
            select(PhysicalTest).where(PhysicalTest.tenant_id == TENANT_ID)
        ).scalars().all())
    print(f"DB'de tenant={TENANT_ID} için toplam {count} test kaydı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
