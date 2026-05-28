"""events: shot + pass + carry + defensive_action raw events (Faz N)

Bir maçtaki tüm event'leri (shot, pass, carry, defensive action) tek bir
tabloda saklar. xT/xA/PPDA/build_up engine'leri bu tablodan okur.

Yüksek hacim: tipik maç ~3000 event × 380 maç/sezon × 10 lig = ~11M satır.
İndeks: (sport, match_external_id), (player_external_id, period).

Idempotency: (tenant_id, sport, source_event_id) unique — adapter'ın
verdiği event_id ile çift insert engellenir.

Revision ID: 0014_events
Revises: 0013_player_appearance_stats
Create Date: 2026-05-28 02:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_events"
down_revision: Union[str, None] = "0013_player_appearance_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    try:
        op.drop_index("ix_events_match", table_name="events")
    except Exception:  # noqa: BLE001
        pass
    try:
        op.drop_index("ix_events_player_period", table_name="events")
    except Exception:  # noqa: BLE001
        pass
    try:
        op.drop_index("ix_events_possession", table_name="events")
    except Exception:  # noqa: BLE001
        pass
    op.drop_table("events")


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="statsbomb_open"),
        # adapter'ın verdiği unique event_id (idempotent ingest)
        sa.Column("source_event_id", sa.String(length=64), nullable=True),
        sa.Column("match_external_id", sa.Integer(), nullable=False),
        sa.Column("team_external_id", sa.Integer(), nullable=True),
        sa.Column("player_external_id", sa.Integer(), nullable=True),
        # event_type: shot|pass|carry|defensive_action
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("minute", sa.Float(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False, server_default="1"),
        # 4 koordinat (pas/carry için end_x/end_y; shot için sadece start)
        sa.Column("start_x", sa.Float(), nullable=True),
        sa.Column("start_y", sa.Float(), nullable=True),
        sa.Column("end_x", sa.Float(), nullable=True),
        sa.Column("end_y", sa.Float(), nullable=True),
        # tip-spesifik flag'ler (shot için body_part/pattern; pass için completed
        # vs.); raw_json içinde tam payload
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("body_part", sa.String(length=32), nullable=True),
        sa.Column("pattern", sa.String(length=32), nullable=True),
        sa.Column("possession_id", sa.Integer(), nullable=True),
        sa.Column("is_goal", sa.Boolean(), nullable=True),
        sa.Column("key_pass", sa.Boolean(), nullable=True),
        # Tam payload (advanced features için)
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "sport", "source", "source_event_id",
            name="uq_events_source_event_id",
        ),
    )
    op.create_index(
        "ix_events_match", "events",
        ["sport", "tenant_id", "match_external_id"],
    )
    op.create_index(
        "ix_events_player_period", "events",
        ["player_external_id", "period"],
    )
    op.create_index(
        "ix_events_possession", "events",
        ["match_external_id", "possession_id"],
    )
