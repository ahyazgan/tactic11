"""tracking_frames: tracking ingest için per-frame kalıcı tablo

Revision ID: 0007_tracking_frames
Revises: 0006_agent_outputs
Create Date: 2026-05-27 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_tracking_frames"
down_revision: Union[str, None] = "0006_agent_outputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracking_frames",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Float(), nullable=False),
        sa.Column("ball_x", sa.Float(), nullable=True),
        sa.Column("ball_y", sa.Float(), nullable=True),
        sa.Column("players_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "sport", "match_external_id", "timestamp",
            name="uq_tracking_frame_unique",
        ),
    )
    op.create_index(
        "ix_tracking_match_time", "tracking_frames",
        ["sport", "match_external_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracking_match_time", table_name="tracking_frames")
    op.drop_table("tracking_frames")
