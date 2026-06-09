"""session_loads — günlük antrenman/maç yükü (AU) kaydı (sRPE/GPS/dakika).

Kaynaktan bağımsız tek yük serisi; ACWR (compute_workload) bu tablodan beslenir.
sRPE (RPE×süre) donanımsız evrensel yöntem; GPS ve dakika-proxy aynı tabloya
`source` etiketiyle yazılır.

Revision ID: 0025_session_loads
Revises: 0024_physical_test_components
Create Date: 2026-06-09 12:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_session_loads"
down_revision: Union[str, None] = "0024_physical_test_components"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_loads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("player_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("player_name", sa.String(length=128), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("load_au", sa.Float(), nullable=False),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("duration_min", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sl_tenant_player", "session_loads", ["tenant_id", "player_id"])
    op.create_index("ix_sl_tenant_date", "session_loads", ["tenant_id", "session_date"])


def downgrade() -> None:
    op.drop_index("ix_sl_tenant_date", table_name="session_loads")
    op.drop_index("ix_sl_tenant_player", table_name="session_loads")
    op.drop_table("session_loads")
