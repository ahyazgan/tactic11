"""snapshots, usage_events, cache_entries

Revision ID: 0002_observability
Revises: 0001_initial
Create Date: 2026-05-27 08:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_observability"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leagues_count", sa.Integer(), nullable=False),
        sa.Column("teams_count", sa.Integer(), nullable=False),
        sa.Column("matches_count", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_snapshots_sport_scope_created",
        "snapshots",
        ["sport", "scope", "created_at"],
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_usage_events_source_created", "usage_events", ["source", "created_at"]
    )

    op.create_table(
        "cache_entries",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source", "key", name="pk_cache_entries"),
    )
    op.create_index("ix_cache_entries_expires", "cache_entries", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_cache_entries_expires", table_name="cache_entries")
    op.drop_table("cache_entries")

    op.drop_index("ix_usage_events_source_created", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_snapshots_sport_scope_created", table_name="snapshots")
    op.drop_table("snapshots")
