"""player_goals — oyuncu hedef/feedback döngü takibi (Faz 5 #38)

Bireysel gelişim için belirlenen hedefler (örn: "pas isabeti %85'e çıksın",
"haftalık 1 yardım"). status: open | in_progress | achieved | missed.
Bir oyuncu birden çok hedefe sahip olabilir; geçmiş kayıt korunur.

Revision ID: 0018_player_goals
Revises: 0017_contracts_and_rehab
Create Date: 2026-05-29 23:50:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_player_goals"
down_revision: Union[str, None] = "0017_contracts_and_rehab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    try:
        op.drop_index("ix_player_goals_player_status", table_name="player_goals")
    except Exception:  # noqa: BLE001
        pass
    op.drop_table("player_goals")


def upgrade() -> None:
    op.create_table(
        "player_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        # status: open | in_progress | achieved | missed
        sa.Column("status", sa.String(length=16),
                  nullable=False, server_default="open"),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_player_goals_player_status", "player_goals",
        ["player_external_id", "status"],
    )
