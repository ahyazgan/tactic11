"""match_load_samples — maç içi, dakika çözünürlüklü oyuncu yükü (GPS/takip).

`session_loads` seans toplamıdır ve "62. dakikada ne kadar koştu" sorusunu
cevaplayamaz. Grup içi "kim çıkar" sorusu olay verisiyle kapandı
(docs/KARNE-GRUP-ICI-SINYAL.md); gereken başka bir veri türü.

Değerler KÜMÜLATİFtir (maç başından o dakikaya). Tersi türetilemeyeceği için
anlık değil kümülatif tutulur.

Revision ID: 0033_match_load_samples
Revises: 0032_performance_targets
Create Date: 2026-09-14 14:10:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_match_load_samples"
down_revision: Union[str, None] = "0032_performance_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "match_load_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("match_external_id", sa.Integer(), nullable=False, index=True),
        sa.Column("player_external_id", sa.Integer(), nullable=False, index=True),
        sa.Column("team_external_id", sa.Integer(), nullable=True),
        sa.Column("minute", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("total_distance_m", sa.Float(), nullable=True),
        sa.Column("high_speed_m", sa.Float(), nullable=True),
        sa.Column("sprint_m", sa.Float(), nullable=True),
        sa.Column("accelerations", sa.Integer(), nullable=True),
        sa.Column("decelerations", sa.Integer(), nullable=True),
        sa.Column("device_load_au", sa.Float(), nullable=True),
        sa.Column("max_speed_ms", sa.Float(), nullable=True),
        sa.Column("speed_thresholds", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "match_external_id", "player_external_id", "minute",
            name="uq_match_load_player_minute",
        ),
    )
    op.create_index(
        "ix_mls_match_minute", "match_load_samples", ["match_external_id", "minute"],
    )


def downgrade() -> None:
    op.drop_index("ix_mls_match_minute", table_name="match_load_samples")
    op.drop_table("match_load_samples")
