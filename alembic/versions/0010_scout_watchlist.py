"""scout_watchlist: scout izleme listesi

Revision ID: 0010_scout_watchlist
Revises: 0009_chat_persistence
Create Date: 2026-05-27 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_scout_watchlist"
down_revision: Union[str, None] = "0009_chat_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_watchlist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "player_external_id",
            name="uq_scout_watchlist_user_player",
        ),
    )
    op.create_index("ix_scout_watchlist_user", "scout_watchlist", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_scout_watchlist_user", table_name="scout_watchlist")
    op.drop_table("scout_watchlist")
