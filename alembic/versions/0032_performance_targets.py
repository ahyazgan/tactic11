"""performance_targets — oyuncu/protokol hedef değeri (hedef takibi).

İlerleme saklanmaz; PhysicalTest geçmişinden (development_curve eğimi) türetilir.

Revision ID: 0032_performance_targets
Revises: 0031_decision_applied
Create Date: 2026-09-11 20:30:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_performance_targets"
down_revision: Union[str, None] = "0031_decision_applied"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "performance_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("player_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("player_name", sa.String(length=128), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ptarget_tenant_player", "performance_targets", ["tenant_id", "player_id"])


def downgrade() -> None:
    op.drop_index("ix_ptarget_tenant_player", table_name="performance_targets")
    op.drop_table("performance_targets")
