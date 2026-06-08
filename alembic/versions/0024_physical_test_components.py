"""physical_tests.components — çok-bileşenli ham veri (JSON, nullable)

Faz 2 türetilmiş metrikleri (RSA Yorgunluk İndeksi'nin 6 sprint süresi, Drop
Jump uçuş/temas süreleri, Triple Hop sol/sağ mesafesi, 505+10m COD bileşenleri)
için ham bileşenleri saklar. `value` türetilmiş metriği (FI/RSI/asimetri%),
`components` ham girdileri tutar. Nullable — eski kayıtlar etkilenmez.

Revision ID: 0024_physical_test_components
Revises: 0023_data_access_user_id_str
Create Date: 2026-06-09 10:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_physical_test_components"
down_revision: Union[str, None] = "0023_data_access_user_id_str"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "physical_tests",
        sa.Column("components", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("physical_tests") as batch_op:
        batch_op.drop_column("components")
