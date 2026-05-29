"""team_goals — sezon hedef takibi (Faz 5 #32)

Takım bazlı sezon hedefleri (örn: "ilk 4'te bitir", "60 puan", "Avrupa
kupasına git"). status: open | in_progress | achieved | missed.
Bir takım × sezon birden çok hedef tutabilir.

Bu migration Sprint 4'ün 0018'i üzerine kurulur — merge sırası önemlidir:
Sprint 3 (0017) → Sprint 4 (0018) → Sprint 5 (0019).

Revision ID: 0019_team_goals
Revises: 0018_player_goals
Create Date: 2026-05-30 00:10:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_team_goals"
down_revision: Union[str, None] = "0018_player_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    try:
        op.drop_index("ix_team_goals_team_season", table_name="team_goals")
    except Exception:  # noqa: BLE001
        pass
    op.drop_table("team_goals")


def upgrade() -> None:
    op.create_table(
        "team_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("team_external_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16),
                  nullable=False, server_default="open"),
        sa.Column("notes", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_team_goals_team_season", "team_goals",
        ["team_external_id", "season"],
    )
