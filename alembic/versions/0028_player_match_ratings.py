"""player_match_ratings: analistin manuel 1-10 maç notları (Maçı Notla)

Performans motorlarını (consistency/trajectory/anomaly/clutch/
opponent_adjusted/team_form_health) event verisi olmadan beslemek için
manuel oyuncu notu kalıcı kaydı.

Idempotent: (tenant, sport, match, player) unique. Maç bağlamı
(opp_rating, fatigue_proxy, flags_json) her satırda denormalize.

Revision ID: 0028_player_match_ratings
Revises: 0027_appearance_season_stats
Create Date: 2026-06-15 16:30:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_player_match_ratings"
down_revision: Union[str, None] = "0027_appearance_season_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    for idx in (
        "ix_player_match_rating_match",
        "ix_player_match_rating_player",
    ):
        try:
            op.drop_index(idx, table_name="player_match_ratings")
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("player_match_ratings")


def upgrade() -> None:
    op.create_table(
        "player_match_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("player_external_id", sa.Integer(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("minute_played", sa.Float(), nullable=False, server_default="90"),
        sa.Column("opp_rating", sa.Float(), nullable=True),
        sa.Column("fatigue_proxy", sa.Float(), nullable=True),
        sa.Column("flags_json", sa.Text(), nullable=True),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "sport", "match_external_id", "player_external_id",
            name="uq_player_match_rating_unique",
        ),
    )
    op.create_index(
        "ix_player_match_rating_player", "player_match_ratings",
        ["tenant_id", "sport", "player_external_id"],
    )
    op.create_index(
        "ix_player_match_rating_match", "player_match_ratings",
        ["tenant_id", "sport", "match_external_id"],
    )
