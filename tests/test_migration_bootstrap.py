"""Revision metadata must accommodate existing long IDs on PostgreSQL."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from alembic import command
from app.core.config import get_settings
from app.db import models
from app.db.migration_bootstrap import bootstrap_version_table
from app.db.session import _normalize_db_url

ROOT = Path(__file__).resolve().parents[1]


def config(output=None):
    result = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    result.set_main_option("script_location", str(ROOT / "alembic"))
    return result


def test_sqlite_bootstrap_preserves_transaction_and_leaves_version_creation_to_alembic():
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            bootstrap_version_table(connection)
            assert connection.get_transaction() is transaction
            assert sa.inspect(connection).get_table_names() == []
            transaction.rollback()
    finally:
        engine.dispose()


def test_postgresql_offline_base_upgrade_can_follow_wide_metadata_prelude(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
    get_settings.cache_clear()
    output = StringIO()
    try:
        command.upgrade(config(output), "0001_initial", sql=True)
    finally:
        get_settings.cache_clear()
    sql = output.getvalue()
    assert "version_num VARCHAR(128) NOT NULL" in sql
    # The prelude commits before domain migrations. Alembic's normal base
    # CREATE is idempotent, so it cannot replace or collide with the wide table.
    assert sql.index("COMMIT;") < sql.index("CREATE TABLE leagues")
    assert "CREATE TABLE alembic_version (" not in sql
    assert sql.count("CREATE TABLE IF NOT EXISTS alembic_version (") == 2
    assert "INSERT INTO alembic_version (version_num) VALUES ('0001_initial')" in sql


@pytest.fixture
def postgres_schema(monkeypatch):
    service = os.getenv("TEST_POSTGRES_URL")
    if not service:
        pytest.skip("isolated PostgreSQL CI service required")
    url = sa.engine.make_url(_normalize_db_url(service))
    assert url.get_backend_name() == "postgresql"
    schema = "revision_bootstrap_" + uuid4().hex
    admin = sa.create_engine(url)
    with admin.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        admin.dispose()
        get_settings.cache_clear()


@pytest.mark.parametrize("width", [None, 32, 256, "text"])
def test_postgresql_bootstrap_preserves_revisions_and_never_narrows(postgres_schema, width):
    engine = postgres_schema
    if width is not None:
        column_type = sa.Text() if width == "text" else sa.String(width)
        table = sa.Table("alembic_version", sa.MetaData(),
                         sa.Column("version_num", column_type, primary_key=True))
        with engine.begin() as connection:
            table.create(connection)
            connection.execute(table.insert().values(version_num="0001_initial"))
    with engine.connect() as connection:
        bootstrap_version_table(connection)
        bootstrap_version_table(connection)
        columns = sa.inspect(connection).get_columns("alembic_version")
        expected_width = 256 if width == 256 else None if width == "text" else 128
        assert columns[0]["type"].length == expected_width
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all() == (
            [] if width is None else ["0001_initial"])
        connection.execute(sa.text("INSERT INTO alembic_version VALUES (:revision)"),
                           {"revision": "0012_tenant_backfill_and_scoped_constraints"})
        connection.commit()


def test_postgresql_upgrade_resumes_from_existing_32_character_version_table(postgres_schema):
    engine = postgres_schema
    command.upgrade(config(), "0001_initial")
    with engine.begin() as connection:
        connection.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"))
    command.upgrade(config(), "head")
    with engine.connect() as connection:
        assert sa.inspect(connection).get_columns("alembic_version")[0]["type"].length == 128
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == (
            ScriptDirectory.from_config(config()).get_current_head())
        assert "players" in sa.inspect(connection).get_table_names()


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_user_foreign_keys_preserve_uuid_on_upgrade_and_downgrade(backend, request, monkeypatch):
    if backend == "postgresql":
        engine = request.getfixturevalue("postgres_schema")
    else:
        path = request.getfixturevalue("tmp_path") / "legacy_note_authors.db"
        url = f"sqlite:///{path}"
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        engine = sa.create_engine(url)
    try:
        command.upgrade(config(), "0034_player_external_ids_bigint")
        with engine.begin() as connection:
            if backend == "sqlite":
                # Recreate the historical permissive INTEGER column, which
                # could contain UUID text even before its type was corrected.
                operations = Operations(MigrationContext.configure(connection))
                with operations.batch_alter_table("notes") as batch:
                    batch.alter_column("author_user_id", existing_type=sa.String(36),
                                       type_=sa.Integer(), existing_nullable=True)
            tenant = connection.execute(sa.select(models.Tenant.id)).scalars().first()
            authors = ["42", "02a2dd86-30c5-455b-91bd-369be9b7ec2d"]
            now = datetime.now(UTC)
            for author in authors:
                connection.execute(models.User.__table__.insert().values(
                    id=author, tenant_id=tenant, email=f"{author}@example.test",
                    password_hash="test-only", role="analyst", active=True, created_at=now,
                ))
                connection.execute(models.Note.__table__.insert().values(
                    tenant_id=tenant, author_user_id=author, subject_type="match", subject_id=1,
                    body=author, created_at=now, updated_at=now,
                ))
                connection.execute(models.DataAccessLog.__table__.insert().values(
                    tenant_id=tenant, user_id=author, subject_type="player", subject_id=1,
                    data_category="test", sensitivity="test", action="read", created_at=now,
                ))
        before = sorted(sa.inspect(engine).get_foreign_keys("notes"),
                        key=lambda fk: fk["constrained_columns"])
        command.upgrade(config(), "head")
        for target in ("0034_player_external_ids_bigint", "0022_physical_tests"):
            command.downgrade(config(), target)
            with engine.connect() as connection:
                assert connection.execute(sa.select(models.Note.author_user_id).order_by(models.Note.id)).scalars().all() == authors
                assert connection.execute(sa.select(models.DataAccessLog.user_id).order_by(models.DataAccessLog.id)).scalars().all() == authors
                columns = {c["name"]: c for c in sa.inspect(connection).get_columns("notes")}
                assert isinstance(columns["author_user_id"]["type"], sa.String)
                assert sorted(sa.inspect(connection).get_foreign_keys("notes"),
                              key=lambda fk: fk["constrained_columns"]) == before
        command.upgrade(config(), "head")
    finally:
        if backend == "sqlite":
            engine.dispose()
        get_settings.cache_clear()
