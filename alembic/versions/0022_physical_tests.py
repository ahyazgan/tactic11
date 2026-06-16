"""physical_tests — oyuncu saha performans testi kayıtları

Sprint/YoYo/CMJ/izokinetik/VO2max/GPS gibi protokollerin ölçüm değerleri.
Oyuncu fiziksel/performans verisi KVKK kapsamında özel nitelikli kişisel veri;
erişim ileride data_access_log üzerinden denetlenebilir.

Revision ID: 0022_physical_tests
Revises: 0021_data_access_log
Create Date: 2026-06-06 14:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_physical_tests"
down_revision: Union[str, None] = "0021_data_access_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    for ix in ("ix_pt_tenant_date", "ix_pt_tenant_player"):
        try:
            op.drop_index(ix)
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("physical_tests")


def upgrade() -> None:
    op.create_table(
        "physical_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("player_id", sa.String(length=64), nullable=False),
        sa.Column("player_name", sa.String(length=128), nullable=False),
        sa.Column("test_date", sa.Date(), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_pt_tenant_player", "physical_tests", ["tenant_id", "player_id"],
    )
    op.create_index(
        "ix_pt_tenant_date", "physical_tests", ["tenant_id", "test_date"],
    )
