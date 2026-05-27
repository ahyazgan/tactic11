"""initial schema: leagues, teams, players, matches

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.UniqueConstraint(
            "sport", "external_id", "season", name="uq_leagues_sport_extid_season"
        ),
    )
    op.create_index("ix_leagues_sport", "leagues", ["sport"])
    op.create_index("ix_leagues_external_id", "leagues", ["external_id"])
    op.create_index("ix_leagues_season", "leagues", ["season"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("founded", sa.Integer(), nullable=True),
        sa.UniqueConstraint("sport", "external_id", name="uq_teams_sport_extid"),
    )
    op.create_index("ix_teams_sport", "teams", ["sport"])
    op.create_index("ix_teams_external_id", "teams", ["external_id"])

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=8), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("nationality", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("sport", "external_id", name="uq_players_sport_extid"),
    )
    op.create_index("ix_players_sport", "players", ["sport"])
    op.create_index("ix_players_external_id", "players", ["external_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("league_external_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("home_team_external_id", sa.Integer(), nullable=False),
        sa.Column("away_team_external_id", sa.Integer(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.UniqueConstraint("sport", "external_id", name="uq_matches_sport_extid"),
    )
    op.create_index("ix_matches_sport", "matches", ["sport"])
    op.create_index("ix_matches_external_id", "matches", ["external_id"])
    op.create_index(
        "ix_matches_league_season", "matches", ["league_external_id", "season"]
    )
    op.create_index("ix_matches_kickoff", "matches", ["kickoff"])


def downgrade() -> None:
    op.drop_index("ix_matches_kickoff", table_name="matches")
    op.drop_index("ix_matches_league_season", table_name="matches")
    op.drop_index("ix_matches_external_id", table_name="matches")
    op.drop_index("ix_matches_sport", table_name="matches")
    op.drop_table("matches")

    op.drop_index("ix_players_external_id", table_name="players")
    op.drop_index("ix_players_sport", table_name="players")
    op.drop_table("players")

    op.drop_index("ix_teams_external_id", table_name="teams")
    op.drop_index("ix_teams_sport", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_leagues_season", table_name="leagues")
    op.drop_index("ix_leagues_external_id", table_name="leagues")
    op.drop_index("ix_leagues_sport", table_name="leagues")
    op.drop_table("leagues")
