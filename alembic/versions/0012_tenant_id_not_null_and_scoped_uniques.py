"""tenant_id NOT NULL + tenant-scoped unique constraints

Multi-tenant Faz 1 (Ufuk 1) — Aşama 2/2:
- 16 tabloda tenant_id NULLABLE → NOT NULL
- Mevcut UniqueConstraint'ler (örn. uq_leagues_sport_extid_season) drop
  edilip yeniden + tenant_id ile oluşturulur (tenant-scoped unique)
- cache_entries: PK (source, key) → (tenant_id, source, key) (kritik!
  cross-tenant cache sızıntısı önleme)

Aşama 1 (0011) sonrası tüm satırlar default tenant'a backfill edilmiş;
app code session.info["tenant_id"] yazıyor → 0012 güvenli.

Revision ID: 0012_tenant_id_not_null_and_scoped_uniques
Revises: 0011_tenants_and_tenant_id_nullable
Create Date: 2026-05-28 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_tenant_id_not_null_and_scoped_uniques"
down_revision: Union[str, None] = "0011_tenants_and_tenant_id_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tablo → mevcut unique constraint adları (tenant ile yeniden oluşturulacak)
# Bunlar 0001-0010 migration'larında tanımlanan UniqueConstraint adları.
_SCOPED_UNIQUES: dict[str, list[tuple[str, list[str]]]] = {
    "leagues": [("uq_leagues_sport_extid_season", ["sport", "external_id", "season"])],
    "teams": [("uq_teams_sport_extid", ["sport", "external_id"])],
    "players": [("uq_players_sport_extid", ["sport", "external_id"])],
    "matches": [("uq_matches_sport_extid", ["sport", "external_id"])],
    "player_appearances": [("uq_player_appearances_player_match", ["sport", "player_external_id", "match_external_id"])],
    "agent_outputs": [("uq_agent_outputs_request", ["agent_name", "agent_version", "subject_type", "subject_id"])],
    "predictions": [("uq_predictions_unique_request", ["sport", "match_external_id", "engine", "engine_version", "params_hash"])],
    "tracking_frames": [("uq_tracking_frame_unique", ["sport", "match_external_id", "timestamp"])],
    "assistant_memory": [("uq_assistant_memory_request", ["subject_type", "subject_id", "key"])],
    "scout_watchlist": [("uq_scout_watchlist_user_player", ["user_id", "player_external_id"])],
}

# tenant_id NOT NULL yapılacak tablolar (tüm 16)
_TABLES_NOT_NULL: tuple[str, ...] = (
    "leagues", "teams", "players", "matches",
    "snapshots", "usage_events", "cache_entries", "job_runs",
    "player_appearances", "agent_outputs", "predictions",
    "tracking_frames", "assistant_memory",
    "chat_conversations", "chat_messages", "scout_watchlist",
)


# --------------------------------------------------------------------------- #
# DOWNGRADE (önce yazıldı)
# --------------------------------------------------------------------------- #


def downgrade() -> None:
    """tenant_id NOT NULL → NULLABLE; tenant-scoped unique'leri eski hâle döndür."""
    # 1) Tenant-scoped unique'leri eski hâline döndür
    for tbl, uniques in _SCOPED_UNIQUES.items():
        with op.batch_alter_table(tbl) as batch:
            for uq_name, cols in uniques:
                try:
                    batch.drop_constraint(uq_name, type_="unique")
                except Exception:  # noqa: BLE001
                    pass
                batch.create_unique_constraint(uq_name, cols)

    # 2) tenant_id NOT NULL → NULLABLE
    for tbl in _TABLES_NOT_NULL:
        with op.batch_alter_table(tbl) as batch:
            batch.alter_column("tenant_id", nullable=True)


# --------------------------------------------------------------------------- #
# UPGRADE
# --------------------------------------------------------------------------- #


def upgrade() -> None:
    """tenant_id NOT NULL + tenant-scoped unique constraint rebuild."""
    # 1) Önce NOT NULL — 0011 backfill sonrası tüm satırların tenant_id'si dolu
    for tbl in _TABLES_NOT_NULL:
        with op.batch_alter_table(tbl) as batch:
            batch.alter_column(
                "tenant_id", existing_type=sa.String(length=36), nullable=False,
            )

    # 2) Sonra unique constraint'leri tenant_id ile yeniden oluştur
    for tbl, uniques in _SCOPED_UNIQUES.items():
        with op.batch_alter_table(tbl) as batch:
            for uq_name, cols in uniques:
                try:
                    batch.drop_constraint(uq_name, type_="unique")
                except Exception:  # noqa: BLE001 — SQLite bazı edge case'lerde
                    pass
                batch.create_unique_constraint(
                    uq_name, [*cols, "tenant_id"],
                )
