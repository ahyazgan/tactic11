"""player_contracts + player_rehabilitations (Faz 5 #34, #43)

İki yeni tablo:

- player_contracts: oyuncu sözleşme bitiş tarihi izleme. Tek aktif satır
  yeterli; yenileme olunca güncellenir. contract_alerts engine bu tablodan
  okuyup horizon_days içinde bitenleri uyarır. Düşük hacim (kulüp başına
  ~25-40 oyuncu).

- player_rehabilitations: sakatlık → rehab → dönüş izi. Aktif rehab
  programı varsa "doubtful/unavailable", döndüğünde "cleared". Bir oyuncuda
  birden çok geçmiş kayıt olabilir; "active" status sadece bir tane.

İki tablo da tenant-scoped, soft delete yok (history kalsın).

Revision ID: 0017_contracts_and_rehab
Revises: 0016_context_layer
Create Date: 2026-05-29 23:30:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_contracts_and_rehab"
down_revision: Union[str, None] = "0016_context_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    for ix in (
        "ix_player_contracts_end",
        "ix_player_rehabilitations_player_status",
    ):
        try:
            op.drop_index(ix)
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("player_rehabilitations")
    op.drop_table("player_contracts")


def upgrade() -> None:
    op.create_table(
        "player_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("team_external_id", sa.Integer(), nullable=True),
        sa.Column("contract_end", sa.Date(), nullable=False),
        sa.Column("annual_salary_eur", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "sport", "player_external_id", "tenant_id",
            name="uq_player_contracts_player",
        ),
    )
    op.create_index(
        "ix_player_contracts_end", "player_contracts",
        ["contract_end"],
    )

    op.create_table(
        "player_rehabilitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("injury_type", sa.String(length=128), nullable=False),
        sa.Column("injury_start", sa.Date(), nullable=False),
        sa.Column("expected_return", sa.Date(), nullable=True),
        sa.Column("actual_return", sa.Date(), nullable=True),
        # status: active | recovering | cleared
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_player_rehabilitations_player_status",
        "player_rehabilitations",
        ["player_external_id", "status"],
    )
