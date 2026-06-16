"""context layer: decisions outcome/audit + match_snapshots (Faz 8)

Faz 8 — Bağlam & Güven katmanı:
- decisions tablosuna audit trail alanları: recommended, confidence,
  context_json, outcome, outcome_value, outcome_notes, outcome_recorded_at
  (öneri uygulandı mı + sonuç ne oldu → feedback loop / güven kalibrasyonu).
- match_snapshots tablosu: maç-içi hafıza için tick-tick canlı snapshot;
  match_memory engine'i bu diziyi okuyup zaman-bağlantıları kurar.

Revision ID: 0016_context_layer
Revises: 0015_decisions
Create Date: 2026-05-29 12:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_context_layer"
down_revision: Union[str, None] = "0015_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decisions") as batch:
        batch.add_column(sa.Column("recommended", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch.add_column(sa.Column("context_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("outcome", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("outcome_value", sa.Float(), nullable=True))
        batch.add_column(sa.Column("outcome_notes", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("outcome_recorded_at",
                                   sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "match_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("team_external_id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Float(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("momentum_score", sa.Float(), nullable=True),
        sa.Column("opponent_formation", sa.String(length=16), nullable=True),
        sa.Column("frame_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_match_snapshots_match_minute", "match_snapshots",
        ["sport", "tenant_id", "match_external_id", "team_external_id", "minute"],
    )


def downgrade() -> None:
    try:
        op.drop_index("ix_match_snapshots_match_minute",
                      table_name="match_snapshots")
    except Exception:  # noqa: BLE001
        pass
    op.drop_table("match_snapshots")
    with op.batch_alter_table("decisions") as batch:
        for col in ("outcome_recorded_at", "outcome_notes", "outcome_value",
                    "outcome", "context_json", "confidence", "recommended"):
            try:
                batch.drop_column(col)
            except Exception:  # noqa: BLE001
                pass
