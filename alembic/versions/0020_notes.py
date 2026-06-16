"""notes — çoklu kullanıcı not/yorum (Faz 5 #41)

Threaded notlar herhangi bir konuya (team/player/match/decision) iliştirilir.
parent_note_id ile yanıt zinciri kurulur.

subject_type: "team" | "player" | "match" | "decision" | "agent_output"
(genişletilebilir).

Sprint 3-5 bundle'ları main'e merge edildikten sonra bu migration
0019_team_goals üzerine eklenir (lineer alembic zinciri korunur).

Revision ID: 0020_notes
Revises: 0019_team_goals
Create Date: 2026-05-30 00:30:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_notes"
down_revision: Union[str, None] = "0019_team_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def downgrade() -> None:
    for ix in ("ix_notes_subject", "ix_notes_parent"):
        try:
            op.drop_index(ix)
        except Exception:  # noqa: BLE001
            pass
    op.drop_table("notes")


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("author_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("parent_note_id", sa.Integer(),
                  sa.ForeignKey("notes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("body", sa.String(length=4096), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_notes_subject", "notes",
        ["subject_type", "subject_id"],
    )
    op.create_index("ix_notes_parent", "notes", ["parent_note_id"])
