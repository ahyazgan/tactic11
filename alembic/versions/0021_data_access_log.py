"""data_access_log — KVKK denetim izi (hassas veri erişim logu)

Oyuncu sağlık/performans verisi özel nitelikli kişisel veri. Her erişim
loglanır ki veri sorumlusu 'kim, hangi oyuncunun, hangi kategorideki verisine,
ne zaman erişti' sorusunu cevaplayabilsin + olağandışı toplu erişim tespit
edilebilsin.

Revision ID: 0021_data_access_log
Revises: 0020_notes
Create Date: 2026-06-06 12:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_data_access_log"
down_revision: Union[str, None] = "0020_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    for ix in ("ix_data_access_subject", "ix_data_access_user"):
        try:
            op.drop_index(ix)
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("data_access_log")


def upgrade() -> None:
    op.create_table(
        "data_access_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("data_category", sa.String(length=48), nullable=False),
        sa.Column("sensitivity", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False,
                  server_default="read"),
        sa.Column("endpoint", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_data_access_subject", "data_access_log",
        ["tenant_id", "subject_type", "subject_id", "created_at"],
    )
    op.create_index(
        "ix_data_access_user", "data_access_log",
        ["tenant_id", "user_id", "created_at"],
    )
