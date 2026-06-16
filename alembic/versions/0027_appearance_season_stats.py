"""player_appearances — sezon istatistiği kolonları (gol/asist/müdahale/duel...).

API-Football fixtures/players yanıtında zaten gelen ama şimdiye dek
parse edilmeyen alanlar. Oyuncu özellik (1-20) türetimi sezon toplamlarını
bu kolonlardan aggregate eder (GET /players/{id}/season-stats).

Revision ID: 0027_appearance_season_stats
Revises: 0026_wellness_entries
Create Date: 2026-06-10 12:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_appearance_season_stats"
down_revision: Union[str, None] = "0026_wellness_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "goals",
    "assists",
    "goals_conceded",
    "saves",
    "key_passes",
    "tackles_total",
    "interceptions",
    "duels_total",
    "duels_won",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column(
            "player_appearances", sa.Column(name, sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("player_appearances", name)
