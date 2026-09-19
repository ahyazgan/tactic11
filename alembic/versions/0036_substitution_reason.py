"""player_appearances.substitution_reason — hamle TAKTİK miydi, mecbur muydu?

Kiracının kendi "kim çıkar" önseli `player_appearances`'tan fit ediliyor
(`app/data/loaders/tenant_prior.py`) ve ölçülmüş bir sınırı vardı: tablo
SAKATLIK hamlelerini ayıklayamıyordu. Sakatlık bir karar değil, mecburiyettir;
önsele girince "bu kulüp bu mevkiyi çıkarır" iddiasını seyreltir
(`docs/KARNE-KIRACI-ONSELI.md`, bilinen sınır 1).

Kırmızı kart zaten `red_cards` ile ayırt edilebiliyordu; eksik olan taktik ile
sakatlık ayrımıydı.

NULL = bilinmiyor. Bu göçten ÖNCE kaydedilmiş satırların hepsi NULL kalır ve
geriye dönük "taktik" varsayılmaz — varsayım yapmak, ölçülmemiş bir şeyi
ölçülmüş göstermek olurdu. Fitter NULL'ları kullanmaya devam eder ama kaçının
sebepli olduğunu raporlar.

Revision ID: 0036_substitution_reason
Revises: 0035_note_author_user_id_str
Create Date: 2026-09-19 10:00:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_substitution_reason"
down_revision: Union[str, None] = "0035_note_author_user_id_str"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "player_appearances",
        sa.Column("substitution_reason", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("player_appearances", "substitution_reason")
