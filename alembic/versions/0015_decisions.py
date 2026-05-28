"""decisions: TD'nin maç-içi hamleleri için audit log (Faz P)

Bir maçta yapılan oyuncu değişikliği, formasyon değişikliği, taktiksel
talimat gibi her kararı yakalar. Post-match learning için:
- "Şu dakikadaki sub doğru muydu?" → predict accuracy
- "Bu formation change'ten sonra ne oldu?" → cause-effect
- Pilot kulüpte koçun kararlarının veri-destekli yansıması

Yüksek hacim değil: maç başına ~10-20 karar.
İndeks: (sport, match_external_id, minute).

Revision ID: 0015_decisions
Revises: 0014_events
Create Date: 2026-05-28 14:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_decisions"
down_revision: Union[str, None] = "0014_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    try:
        op.drop_index("ix_decisions_match_minute", table_name="decisions")
    except Exception:  # noqa: BLE001
        pass
    op.drop_table("decisions")


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("team_external_id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Float(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False, server_default="1"),
        # decision_type: substitution|formation_change|tactical_instruction|other
        sa.Column("decision_type", sa.String(length=32), nullable=False),
        # subject_player_id: substitution'da çıkan oyuncu; formation_change'de null
        sa.Column("subject_player_external_id", sa.Integer(), nullable=True),
        # related_player_id: substitution'da giren oyuncu
        sa.Column("related_player_external_id", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("notes", sa.String(length=512), nullable=True),
        sa.Column("by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_decisions_match_minute", "decisions",
        ["sport", "tenant_id", "match_external_id", "minute"],
    )
