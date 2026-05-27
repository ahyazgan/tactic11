"""tenants + users + refresh_tokens + tenant_id NULLABLE on 16 tables

Multi-tenant Faz 1 (Ufuk 1) — Aşama 1/2:
- 3 yeni tablo: tenants, users, refresh_tokens
- 16 mevcut tabloya tenant_id NULLABLE eklenir + index + FK CASCADE
- Default tenant + default admin user seed edilir (backward compat için)
- Mevcut tüm satırlar default tenant'a backfill

Aşama 2/2 (migration 0012): NOT NULL + tenant-scoped unique constraints

Revision ID: 0011_tenants_and_tenant_id_nullable
Revises: 0010_scout_watchlist
Create Date: 2026-05-27 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_tenants_and_tenant_id_nullable"
down_revision: Union[str, None] = "0010_scout_watchlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default tenant — backward-compat için. UUID v4 sabit (test ve seed için
# deterministik). DEFAULT_TENANT_ID değeri app code'unda kullanılır.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# 16 tablo: hangi tablolara tenant_id eklenecek
_TABLES_WITH_TENANT_ID: tuple[str, ...] = (
    "leagues", "teams", "players", "matches",
    "snapshots", "usage_events", "cache_entries", "job_runs",
    "player_appearances", "agent_outputs", "predictions",
    "tracking_frames", "assistant_memory",
    "chat_conversations", "chat_messages", "scout_watchlist",
)


# --------------------------------------------------------------------------- #
# DOWNGRADE — yukarı çıkmadan önce yazıldı (geri alınabilirlik garantisi)
# --------------------------------------------------------------------------- #


def downgrade() -> None:
    """Tüm 16 tablodan tenant_id kolonunu kaldır, sonra 3 yeni tabloyu drop et.

    Dikkat: Tenant izolasyonu kaldırıldığı için downgrade SADECE
    NULLABLE state'inde mümkün. 0012 (NOT NULL) sonrası geri dönüş için
    önce 0012'yi downgrade etmek gerekir.
    """
    bind = op.get_bind()
    for tbl in _TABLES_WITH_TENANT_ID:
        try:
            op.drop_index(f"ix_{tbl}_tenant", table_name=tbl)
        except Exception:  # noqa: BLE001 — bazı dialect'lerde IF EXISTS yok
            pass
        # SQLite naming convention'ı için FK constraint isimleri farklı olabilir;
        # alembic batch mode ile sade drop column.
        with op.batch_alter_table(tbl) as batch:
            try:
                batch.drop_constraint(f"fk_{tbl}_tenant_id", type_="foreignkey")
            except Exception:  # noqa: BLE001
                pass
            batch.drop_column("tenant_id")

    op.drop_index("ix_refresh_tokens_expires", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_tenant", table_name="users")
    op.drop_table("users")

    op.drop_table("tenants")


# --------------------------------------------------------------------------- #
# UPGRADE
# --------------------------------------------------------------------------- #


def upgrade() -> None:
    """3 yeni tablo + 16 tabloya tenant_id NULLABLE + backfill default tenant."""

    # ---- 1) tenants tablosu --------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    # ---- 2) users tablosu ----------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant", "users", ["tenant_id"])

    # ---- 3) refresh_tokens tablosu ------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
    )
    op.create_index("ix_refresh_tokens_user", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires", "refresh_tokens", ["expires_at"])

    # ---- 4) Default tenant seed (backward-compat) ----------------------------
    from datetime import UTC, datetime as _dt
    now_iso = _dt.now(UTC).isoformat()
    op.execute(
        sa.text(
            "INSERT INTO tenants (id, slug, name, settings_json, active, created_at) "
            "VALUES (:id, :slug, :name, :settings, :active, :now)"
        ).bindparams(
            id=DEFAULT_TENANT_ID,
            slug="default",
            name="Default Tenant",
            settings="{}",
            active=True,
            now=now_iso,
        )
    )

    # ---- 5) 16 tabloya tenant_id NULLABLE + index + FK ----------------------
    for tbl in _TABLES_WITH_TENANT_ID:
        with op.batch_alter_table(tbl) as batch:
            batch.add_column(sa.Column(
                "tenant_id", sa.String(length=36), nullable=True,
            ))
            batch.create_foreign_key(
                f"fk_{tbl}_tenant_id", "tenants",
                ["tenant_id"], ["id"], ondelete="CASCADE",
            )
        op.create_index(f"ix_{tbl}_tenant", tbl, ["tenant_id"])

        # Backfill — tüm mevcut satırları default tenant'a ata
        op.execute(
            sa.text(f"UPDATE {tbl} SET tenant_id = :tid WHERE tenant_id IS NULL")
            .bindparams(tid=DEFAULT_TENANT_ID)
        )
