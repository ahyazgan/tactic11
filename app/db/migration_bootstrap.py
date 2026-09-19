"""Prepare PostgreSQL's revision metadata for historical IDs over 32 chars.

This only changes Alembic's own metadata. Applied revision values and domain
tables are untouched; the explicit prelude commits before migration transactions.
"""
from __future__ import annotations

from io import TextIOBase
from typing import TextIO

from sqlalchemy import text
from sqlalchemy.engine import Connection

VERSION_TABLE_STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS alembic_version ("
    "version_num VARCHAR(128) NOT NULL, "
    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))",
    """DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'alembic_version'::regclass AND attname = 'version_num'
          AND atttypid = 'varchar'::regtype AND atttypmod > 0 AND atttypmod < 132
    ) THEN
        ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);
    END IF;
END; $$""",
)


def bootstrap_version_table(connection: Connection) -> None:
    """Create/widen revision storage in the current PostgreSQL search path.

    PostgreSQL's varchar typmod includes four bookkeeping bytes: below 132
    means a limit below 128 characters. Wider or unlimited columns stay wider.
    Call on a fresh connection, before Alembic owns its migration transaction.
    """
    if connection.dialect.name != "postgresql":
        return
    if connection.in_transaction():
        raise ValueError("Version metadata bootstrap must precede the migration transaction")
    with connection.begin():
        for statement in VERSION_TABLE_STATEMENTS:
            connection.execute(text(statement))


def write_version_table_prelude(output: TextIO) -> None:
    """Emit the same separately committed prelude in PostgreSQL offline SQL."""
    output.write("BEGIN;\n\n")
    for statement in VERSION_TABLE_STATEMENTS:
        output.write(statement + ";\n\n")
    output.write("COMMIT;\n\n")
    output.flush()


class VersionTableOutput(TextIOBase):
    """Public output-buffer adapter for Alembic's offline base-table CREATE.

    Alembic emits its own default-width CREATE when starting from base even
    though the prelude already created the table. Make only that reserved
    metadata CREATE idempotent; other generated SQL passes through unchanged.
    No migration context internals or globally registered compilers are changed.
    """

    def __init__(self, output: TextIO) -> None:
        super().__init__()
        self.output = output

    def write(self, value: str) -> int:
        prefix = "CREATE TABLE alembic_version ("
        if value.startswith(prefix):
            value_out = value.replace(prefix, "CREATE TABLE IF NOT EXISTS alembic_version (", 1)
        else:
            value_out = value
        self.output.write(value_out)
        return len(value)

    def flush(self) -> None:
        self.output.flush()

    def writable(self) -> bool:
        return True
