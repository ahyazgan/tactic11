"""chat_conversations + chat_messages: asistan konuşma geçmişi

Revision ID: 0009_chat_persistence
Revises: 0008_assistant_memory
Create Date: 2026-05-27 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_chat_persistence"
down_revision: Union[str, None] = "0008_assistant_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_external_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_conversations_team", "chat_conversations", ["team_external_id"],
    )
    op.create_index(
        "ix_chat_conversations_updated", "chat_conversations", ["updated_at"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("tool_traces_json", sa.Text(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_messages_conv_seq", "chat_messages",
        ["conversation_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conv_seq", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_conversations_updated", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_team", table_name="chat_conversations")
    op.drop_table("chat_conversations")
