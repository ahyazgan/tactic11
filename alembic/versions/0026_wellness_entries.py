"""wellness_entries — öznel günlük hazırlık anketi (5 madde 1-7 + readiness).

ACWR (objektif yük) ile birlikte Hazırlık Kararı'nın öznel yarısı.

Revision ID: 0026_wellness_entries
Revises: 0025_session_loads
Create Date: 2026-06-09 13:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_wellness_entries"
down_revision: Union[str, None] = "0025_session_loads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wellness_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("player_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("player_name", sa.String(length=128), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("sleep_quality", sa.Integer(), nullable=False),
        sa.Column("fatigue", sa.Integer(), nullable=False),
        sa.Column("muscle_soreness", sa.Integer(), nullable=False),
        sa.Column("stress", sa.Integer(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=False),
        sa.Column("readiness", sa.Float(), nullable=False),
        sa.Column("recorded_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_we_tenant_player", "wellness_entries", ["tenant_id", "player_id"])
    op.create_index("ix_we_tenant_date", "wellness_entries", ["tenant_id", "entry_date"])


def downgrade() -> None:
    op.drop_index("ix_we_tenant_date", table_name="wellness_entries")
    op.drop_index("ix_we_tenant_player", table_name="wellness_entries")
    op.drop_table("wellness_entries")
