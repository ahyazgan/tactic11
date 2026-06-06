"""data_access_log.user_id Integer → String(36) (User.id ile uyum)

User.id String(36) (UUID) iken DataAccessLog.user_id Integer'dı → FK tip
uyumsuzluğu ve 'kim erişti' saklanamıyordu. KVKK denetimi için "kim" kritik;
kolon User.id ile aynı tipe çekiliyor.

Revision ID: 0023_data_access_user_id_str
Revises: 0022_physical_tests
Create Date: 2026-06-06 15:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_data_access_user_id_str"
down_revision: Union[str, None] = "0022_physical_tests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch: SQLite tablo-kopyalar, Postgres ALTER üretir (USING ile cast).
    with op.batch_alter_table("data_access_log") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            type_=sa.String(length=36),
            existing_nullable=True,
            postgresql_using="user_id::varchar(36)",
        )


def downgrade() -> None:
    with op.batch_alter_table("data_access_log") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.String(length=36),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using="user_id::integer",
        )
