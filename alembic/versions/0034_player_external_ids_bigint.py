"""Keep segment-scoped tracking IDs intact in every player identity consumer.

Revision ID: 0034_player_external_ids_bigint
Revises: 0033_match_load_samples

The 30-second segment's first anonymous player is 30,000,030,001, already
larger than PostgreSQL INTEGER. Only external player identity values widen;
surrogate primary keys, their foreign keys and match/team IDs do not change.

Rollback requires every affected value to fit signed int32. Remap or archive
out-of-range identities explicitly before downgrading. Never truncate, wrap
or silently rewrite identity values. All columns are checked before any ALTER.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034_player_external_ids_bigint"
down_revision: str | None = "0033_match_load_samples"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Historical migration constants: do not import the changing ORM schema.
_COLUMNS: tuple[tuple[str, tuple[tuple[str, bool], ...]], ...] = (
    ("players", (("external_id", False),)),
    ("player_appearances", (("player_external_id", False),)),
    ("tracking_identities", (
        ("track_player_external_id", False), ("player_external_id", True),
    )),
    ("scout_watchlist", (("player_external_id", False),)),
    ("events", (("player_external_id", True),)),
    ("decisions", (
        ("subject_player_external_id", True), ("related_player_external_id", True),
    )),
    ("player_contracts", (("player_external_id", False),)),
    ("player_rehabilitations", (("player_external_id", False),)),
    ("player_goals", (("player_external_id", False),)),
    ("player_match_ratings", (("player_external_id", False),)),
    ("match_load_samples", (("player_external_id", False),)),
)
_INT32_MIN, _INT32_MAX = -(1 << 31), (1 << 31) - 1


def upgrade() -> None:
    for table, columns in _COLUMNS:
        # Native ALTER on PostgreSQL; SQLite preserves constraints with a batch.
        with op.batch_alter_table(table) as batch:
            for column, nullable in columns:
                batch.alter_column(
                    column, existing_type=sa.Integer(), type_=sa.BigInteger(),
                    existing_nullable=nullable,
                )


def _check_int32_range() -> None:
    context = op.get_context()
    if context.as_sql:
        if context.dialect.name != "postgresql":
            raise RuntimeError("Offline downgrade requires PostgreSQL; validate other databases online")
        # This check runs when the generated script runs, not when SQL is emitted.
        checks = []
        for table, columns in _COLUMNS:
            for column, _ in columns:
                checks.append(
                    f"IF EXISTS (SELECT 1 FROM {table} WHERE {column} < {_INT32_MIN} "
                    f"OR {column} > {_INT32_MAX}) THEN\n"
                    f"RAISE EXCEPTION 'Cannot downgrade {table}.{column}: "
                    "values exceed signed int32; remap or archive them first';\nEND IF;"
                )
        op.execute(sa.text("DO $$ BEGIN\n" + "\n".join(checks) + "\nEND; $$;"))
        return

    connection = op.get_bind()
    for table_name, columns in _COLUMNS:
        table = sa.table(table_name, *(sa.column(name, sa.BigInteger()) for name, _ in columns))
        for column_name, _ in columns:
            column = table.c[column_name]
            invalid = connection.execute(
                sa.select(column).where(sa.or_(column < _INT32_MIN, column > _INT32_MAX)).limit(1)
            ).first()
            if invalid is not None:
                raise RuntimeError(
                    f"Cannot downgrade {table_name}.{column_name}: values exceed signed int32; "
                    "remap or archive them first"
                )


def downgrade() -> None:
    _check_int32_range()
    for table, columns in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            for column, nullable in columns:
                batch.alter_column(
                    column, existing_type=sa.BigInteger(), type_=sa.Integer(),
                    existing_nullable=nullable,
                )
