"""player_appearances: oyuncu yük analizi için dakika kayıtları

Revision ID: 0005_player_appearances
Revises: 0004_predictions
Create Date: 2026-05-27 17:35:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_player_appearances"
down_revision: Union[str, None] = "0004_predictions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_appearances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "sport", "player_external_id", "match_external_id",
            name="uq_player_appearances_player_match",
        ),
    )
    op.create_index(
        "ix_player_appearances_player_kickoff",
        "player_appearances",
        ["player_external_id", "kickoff"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_player_appearances_player_kickoff", table_name="player_appearances"
    )
    op.drop_table("player_appearances")
