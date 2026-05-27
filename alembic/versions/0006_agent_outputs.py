"""agent_outputs: proaktif agent sonuçları için kalıcı tablo

Revision ID: 0006_agent_outputs
Revises: 0005_player_appearances
Create Date: 2026-05-27 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_agent_outputs"
down_revision: Union[str, None] = "0005_player_appearances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=16), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "agent_name", "agent_version", "subject_type", "subject_id",
            name="uq_agent_outputs_request",
        ),
    )
    op.create_index(
        "ix_agent_outputs_agent_subject", "agent_outputs",
        ["agent_name", "subject_type", "subject_id"],
    )
    op.create_index(
        "ix_agent_outputs_updated", "agent_outputs", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_outputs_updated", table_name="agent_outputs")
    op.drop_index("ix_agent_outputs_agent_subject", table_name="agent_outputs")
    op.drop_table("agent_outputs")
