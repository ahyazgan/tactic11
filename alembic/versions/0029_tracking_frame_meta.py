"""tracking_frames.meta_json: event-bağlantılı frame meta'sı

StatsBomb 360 gibi event-çapalı tracking kaynakları için frame başına
event_uuid / event_type / possession_team / visible_area / source bilgisi.
Sürekli tracking sağlayıcılarında NULL kalır.

Revision ID: 0029_tracking_frame_meta
Revises: 0028_player_match_ratings
Create Date: 2026-09-08 22:30:00
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_tracking_frame_meta"
down_revision: Union[str, None] = "0028_player_match_ratings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tracking_frames",
        sa.Column("meta_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracking_frames", "meta_json")
