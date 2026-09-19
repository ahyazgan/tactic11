"""Align previously installed note authors with the users UUID key.

Corrected 0020 creates VARCHAR(36) on fresh installs. This revision also repairs
existing SQLite installations, whose permissive INTEGER columns could already
contain UUID text. Neither numeric legacy identifiers nor UUIDs are discarded.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0035_note_author_user_id_str"
down_revision: str | None = "0034_player_external_ids_bigint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notes") as batch:
        batch.alter_column(
            "author_user_id", existing_type=sa.Integer(), type_=sa.String(36),
            existing_nullable=True, postgresql_using="author_user_id::varchar(36)",
        )


def downgrade() -> None:
    # The corrected predecessor schema also uses VARCHAR(36). Keep that valid
    # FK type and all author values; restoring INTEGER would invalidate UUIDs.
    pass
