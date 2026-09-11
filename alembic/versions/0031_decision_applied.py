"""decision_applied: koçun öneriyi sahada uygulayıp uygulamadığı işareti

`decisions.outcome` "karardan sonra ne oldu"yu ölçüyor; "öneri YÜZÜNDEN ne
oldu" ancak uygulanan ile uygulanmayan öneriler kıyaslanınca ölçülebilir.
Ölçüldü (502 karar, gerçek maçlar): uygulanmamış önerilerde hiçbir sinyal
sonucu ayırmıyor — karşı-olgu yok. Bu alan o karşı-olguyu kaydeder.

  applied     : True = uyguladım · False = uygulamadım · NULL = bilinmiyor
  applied_at  : işaretin konduğu an

Eski kayıtlar NULL kalır: geçmişte kimse işaretlemedi, uydurulmaz. Geri
besleme (isabet oranı, kalibrasyon) yalnız `applied IS TRUE` satırlardan
öğrenir; NULL satırlar bilerek dışarıda kalır.

Revision ID: 0031_decision_applied
Revises: 0030_tracking_identities
Create Date: 2026-09-11 09:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_decision_applied"
down_revision: str | None = "0030_tracking_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("applied", sa.Boolean(), nullable=True))
    op.add_column(
        "decisions",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("decisions", "applied_at")
    op.drop_column("decisions", "applied")
