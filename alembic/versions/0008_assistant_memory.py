"""assistant_memory: yardımcı manager asistanın kalıcı hafızası

Revision ID: 0008_assistant_memory
Revises: 0007_tracking_frames
Create Date: 2026-05-27 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_assistant_memory"
down_revision: Union[str, None] = "0007_tracking_frames"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "subject_type", "subject_id", "key",
            name="uq_assistant_memory_request",
        ),
    )
    op.create_index(
        "ix_assistant_memory_subject", "assistant_memory",
        ["subject_type", "subject_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_memory_subject", table_name="assistant_memory")
    op.drop_table("assistant_memory")
