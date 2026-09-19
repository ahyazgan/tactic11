"""Historical bootstrap must use native Boolean literals on PostgreSQL."""
from __future__ import annotations

import importlib.util
import re
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_tenant_bootstrap_postgresql_defaults_and_seed_are_boolean_not_integer():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0011_tenants_and_tenant_id_nullable.py"
    spec = importlib.util.spec_from_file_location("tenant_bootstrap_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "literal_binds": True, "output_buffer": output},
    )
    with Operations.context(context):
        migration.upgrade()
    sql = output.getvalue()
    # Compile the actual historical migration, including its seed, without
    # requiring a server. SQLite's permissive BOOLEAN DEFAULT 1 hid this bug.
    assert sql.count("active BOOLEAN DEFAULT true NOT NULL") == 2
    assert not re.search(r"BOOLEAN DEFAULT ['\"]?[01]", sql)
    seed = next(line for line in sql.splitlines() if line.startswith("INSERT INTO tenants"))
    assert ", true, " in seed
    assert migration.DEFAULT_TENANT_ID in seed
