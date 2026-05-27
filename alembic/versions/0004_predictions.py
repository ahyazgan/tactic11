"""predictions: engine tahminleri + reconciliation

Revision ID: 0004_predictions
Revises: 0003_scheduler
Create Date: 2026-05-27 17:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_predictions"
down_revision: Union[str, None] = "0003_scheduler"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=16), nullable=False),
        sa.Column("params_hash", sa.String(length=64), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("predicted_value_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_home_score", sa.Integer(), nullable=True),
        sa.Column("actual_away_score", sa.Integer(), nullable=True),
        sa.Column("actual_outcome", sa.String(length=4), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "sport", "match_external_id", "engine", "engine_version", "params_hash",
            name="uq_predictions_unique_request",
        ),
    )
    op.create_index("ix_predictions_match", "predictions", ["sport", "match_external_id"])
    op.create_index(
        "ix_predictions_engine_version", "predictions", ["engine", "engine_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_predictions_engine_version", table_name="predictions")
    op.drop_index("ix_predictions_match", table_name="predictions")
    op.drop_table("predictions")
