"""PostgreSQL width checks plus isolated, data-preserving migration rollback.

SQLite alone accepts int64 values even in an INTEGER column. Its successful
inserts therefore cannot catch the production overflow: PostgreSQL DDL must
also compile these external identity columns as BIGINT.
"""
from __future__ import annotations

import importlib.util
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateColumn

from alembic import command
from app.core.config import get_settings
from app.db import models
from app.db.base import Base
from app.db.match_load import MatchLoadSample

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0034_player_external_ids_bigint"
PREVIOUS = "0033_match_load_samples"
LARGE_ID = 30_000_030_001  # first video player, segment offset 30 seconds
EXPECTED = {
    "players": {"external_id"},
    "player_appearances": {"player_external_id"},
    "tracking_identities": {"track_player_external_id", "player_external_id"},
    "scout_watchlist": {"player_external_id"},
    "events": {"player_external_id"},
    "decisions": {"subject_player_external_id", "related_player_external_id"},
    "player_contracts": {"player_external_id"},
    "player_rehabilitations": {"player_external_id"},
    "player_goals": {"player_external_id"},
    "player_match_ratings": {"player_external_id"},
    "match_load_samples": {"player_external_id"},
}


def test_external_player_domain_compiles_to_postgresql_bigint_without_widening_row_keys():
    actual = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("player_external_id")
        or (table.name == "players" and column.name == "external_id")
    }
    assert actual == {(table, column) for table, columns in EXPECTED.items() for column in columns}
    for table_name, column_names in EXPECTED.items():
        table = Base.metadata.tables[table_name]
        for name in column_names:
            assert isinstance(table.c[name].type, sa.BigInteger), (table_name, name)
            assert "BIGINT" in str(CreateColumn(table.c[name]).compile(dialect=postgresql.dialect()))
        assert type(table.c.id.type) is sa.Integer
        for column in table.columns:
            if column.name in {"match_external_id", "team_external_id"}:
                assert type(column.type) is sa.Integer


def _migration():
    spec = importlib.util.spec_from_file_location(REVISION, ROOT / "alembic/versions" / f"{REVISION}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _postgresql_sql(action: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        getattr(_migration(), action)()
    return output.getvalue()


def test_postgresql_migration_sql_widens_all_columns_and_checks_before_any_narrowing():
    upgrade, downgrade = _postgresql_sql("upgrade"), _postgresql_sql("downgrade")
    for table, columns in EXPECTED.items():
        for column in columns:
            assert f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BIGINT" in upgrade
            assert f"ALTER TABLE {table} ALTER COLUMN {column} TYPE INTEGER" in downgrade
            assert f"FROM {table} WHERE {column} < -2147483648 OR {column} > 2147483647" in downgrade
    assert downgrade.rfind("RAISE EXCEPTION") < downgrade.index("ALTER TABLE")
    assert "remap or archive them first" in downgrade
    assert "DROP" not in upgrade


def test_offline_non_postgresql_downgrade_refuses_to_skip_range_validation():
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="sqlite", opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context), pytest.raises(RuntimeError, match="validate other databases online"):
        _migration().downgrade()
    assert output.getvalue() == ""


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"), reason="isolated PostgreSQL CI service required"))])
def migrated_db(tmp_path, monkeypatch, request):
    admin = None
    schema = None
    url = f"sqlite:///{tmp_path / 'player_id_migration.db'}"
    if request.param == "postgresql":
        from app.db.session import _normalize_db_url

        # Each test owns a fresh schema; never migrate a configured live schema.
        service_url = sa.engine.make_url(_normalize_db_url(os.environ["TEST_POSTGRES_URL"]))
        assert service_url.get_backend_name() == "postgresql"
        admin = sa.create_engine(service_url)
        schema = "identity_migration_" + uuid4().hex
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        # Avoid percent-encoded URL options crossing ConfigParser interpolation
        # in historical Alembic env.py. libpq applies this to its new connections.
        monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
        url = service_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, PREVIOUS)
        yield config, engine
    finally:
        engine.dispose()
        if admin is not None and schema is not None:
            with admin.begin() as connection:
                connection.execute(sa.schema.DropSchema(schema, cascade=True))
            admin.dispose()
        get_settings.cache_clear()


def _structure(engine):
    inspector = sa.inspect(engine)
    return {
        name: {
            "indexes": inspector.get_indexes(name),
            "uniques": inspector.get_unique_constraints(name),
            "foreign_keys": inspector.get_foreign_keys(name),
            "primary_key": inspector.get_pk_constraint(name),
            "nullability": {c["name"]: c["nullable"] for c in inspector.get_columns(name)},
        }
        for name in EXPECTED
    }


def _assert_width(engine, expected_type):
    inspector = sa.inspect(engine)
    for table, names in EXPECTED.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        for name in names:
            assert isinstance(columns[name]["type"], expected_type)
            if expected_type is sa.Integer:
                assert not isinstance(columns[name]["type"], sa.BigInteger)
        assert not isinstance(columns["id"]["type"], sa.BigInteger)


def test_migration_roundtrip_preserves_existing_rows_indexes_nulls_and_integer_primary_keys(migrated_db):
    config, engine = migrated_db
    before = _structure(engine)
    with Session(engine) as session:
        tenant_id = session.execute(sa.select(models.Tenant.id)).scalars().first()
        assert tenant_id is not None  # the historical tenant migration seeds one
        player = models.Player(sport="football", external_id=77, name="Existing player", tenant_id=tenant_id)
        identity = models.TrackingIdentity(
            sport="football", match_external_id=117093, track_player_external_id=30001,
            player_external_id=None, player_name="Anonymous", updated_at=datetime.now(UTC),
        )
        session.add_all([player, identity])
        session.commit()
        row_ids = player.id, identity.id

    command.upgrade(config, REVISION)
    _assert_width(engine, sa.BigInteger)
    assert _structure(engine) == before
    with Session(engine) as session:
        player = session.get(models.Player, row_ids[0])
        identity = session.get(models.TrackingIdentity, row_ids[1])
        assert player is not None and player.external_id == 77
        assert identity is not None and identity.track_player_external_id == 30001
        assert identity.player_external_id is None
        second = models.Player(sport="football", external_id=(1 << 31) - 1, name="Upper limit", tenant_id=tenant_id)
        third = models.Player(sport="football", external_id=-(1 << 31), name="Lower limit", tenant_id=tenant_id)
        session.add_all([second, third])
        session.commit()
        assert second.id > player.id and third.id > second.id  # SQLite rowid still autoincrements

    command.downgrade(config, PREVIOUS)
    _assert_width(engine, sa.Integer)
    assert _structure(engine) == before
    with engine.connect() as connection:
        assert connection.execute(sa.select(models.Player.external_id).order_by(models.Player.id)).scalars().all() == [
            77, (1 << 31) - 1, -(1 << 31),
        ]
    command.upgrade(config, REVISION)
    _assert_width(engine, sa.BigInteger)


@pytest.mark.parametrize("bad_id", [LARGE_ID, -(1 << 31) - 1])
def test_downgrade_checks_last_table_before_changing_any_column(migrated_db, bad_id):
    config, engine = migrated_db
    command.upgrade(config, REVISION)
    with Session(engine) as session:
        session.add(MatchLoadSample(
            match_external_id=117093, player_external_id=bad_id, minute=1.0,
            source="tracking", created_at=datetime.now(UTC),
        ))
        session.commit()
    with pytest.raises(RuntimeError, match=r"match_load_samples.player_external_id.*signed int32"):
        command.downgrade(config, PREVIOUS)
    _assert_width(engine, sa.BigInteger)
    with engine.connect() as connection:
        assert connection.execute(sa.select(MatchLoadSample.player_external_id)).scalar_one() == bad_id
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
