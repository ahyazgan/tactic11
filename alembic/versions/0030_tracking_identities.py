"""tracking_identities: video takibi sentetik takip id'si → gerçek oyuncu eşlemesi

Analist Video Analiz ekranında takibi (30000+track_id) kadrodaki oyuncuya bağlar;
/tracking kareleri servis edilirken isim + gerçek id uygulanır.

Revision ID: 0030_tracking_identities
Revises: 0029_tracking_frame_meta
Create Date: 2026-09-09 02:10:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_tracking_identities"
down_revision: str | None = "0029_tracking_frame_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracking_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("track_player_external_id", sa.Integer(), nullable=False),
        sa.Column("player_external_id", sa.Integer(), nullable=True),
        sa.Column("player_name", sa.String(length=120), nullable=False),
        sa.Column("jersey_number", sa.Integer(), nullable=True),
        sa.Column("team_external_id", sa.Integer(), nullable=True),
        sa.Column("is_keeper", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "sport", "match_external_id", "track_player_external_id",
            name="uq_tracking_identity_unique",
        ),
    )
    op.create_index(
        "ix_tracking_identity_match", "tracking_identities",
        ["tenant_id", "sport", "match_external_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracking_identity_match", table_name="tracking_identities")
    op.drop_table("tracking_identities")
