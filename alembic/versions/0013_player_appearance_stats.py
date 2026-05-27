"""player_appearances: full API-Football match stats (Prompt 4)

Revision ID: 0013_player_appearance_stats
Revises: 0012_tenant_id_not_null_and_scoped_uniques
Create Date: 2026-05-28 01:00:00

Yeni kolonlar (hepsi nullable — eski satırlar için sorun yok):
- rating_apifootball NUMERIC(3,1)
- passes_total, passes_accuracy
- shots_total, shots_on
- dribbles_attempts, dribbles_success
- fouls_committed, fouls_drawn
- yellow_cards, red_cards, second_yellow BOOL
- substituted_in_minute, substituted_out_minute
- position_played VARCHAR(5)
- formation_played VARCHAR(10)
- captain BOOL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_player_appearance_stats"
down_revision: Union[str, None] = "0012_tenant_id_not_null_and_scoped_uniques"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = [
    sa.Column("rating_apifootball", sa.Float(), nullable=True),
    sa.Column("passes_total", sa.Integer(), nullable=True),
    sa.Column("passes_accuracy", sa.Integer(), nullable=True),
    sa.Column("shots_total", sa.Integer(), nullable=True),
    sa.Column("shots_on", sa.Integer(), nullable=True),
    sa.Column("dribbles_attempts", sa.Integer(), nullable=True),
    sa.Column("dribbles_success", sa.Integer(), nullable=True),
    sa.Column("fouls_committed", sa.Integer(), nullable=True),
    sa.Column("fouls_drawn", sa.Integer(), nullable=True),
    sa.Column("yellow_cards", sa.Integer(), nullable=True),
    sa.Column("red_cards", sa.Integer(), nullable=True),
    sa.Column("second_yellow", sa.Boolean(), nullable=True),
    sa.Column("substituted_in_minute", sa.Integer(), nullable=True),
    sa.Column("substituted_out_minute", sa.Integer(), nullable=True),
    sa.Column("position_played", sa.String(length=5), nullable=True),
    sa.Column("formation_played", sa.String(length=10), nullable=True),
    sa.Column("captain", sa.Boolean(), nullable=True),
    # team_external_id — appearance hangi takım için (PlayerAppearance bunu tutmuyordu;
    # lineup adapter doldurur, scout/load engine'leri kullanır)
    sa.Column("team_external_id", sa.Integer(), nullable=True),
]


def downgrade() -> None:
    try:
        op.drop_index(
            "ix_player_appearances_team_kickoff",
            table_name="player_appearances",
        )
    except Exception:  # noqa: BLE001
        pass
    with op.batch_alter_table("player_appearances") as batch:
        for col in reversed(_NEW_COLUMNS):
            batch.drop_column(col.name)


def upgrade() -> None:
    with op.batch_alter_table("player_appearances") as batch:
        for col in _NEW_COLUMNS:
            batch.add_column(col)
    op.create_index(
        "ix_player_appearances_team_kickoff", "player_appearances",
        ["team_external_id", "kickoff"],
    )
