"""Boş veritabanında her tablo açılmalı: tablo tanımlayan modül listede yoksa ucu 500 verir."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.dev_seed import MODEL_MODULES

ROOT = Path(__file__).resolve().parents[1]


def test_every_table_module_is_listed():
    defining = {f"app.db.{p.stem}" for p in (ROOT / "app" / "db").glob("*.py")
                if re.search(r"^\s+__tablename__\s*=", p.read_text(encoding="utf-8"), re.M)}
    assert defining == set(MODEL_MODULES)


def test_fresh_process_creates_the_tables_of_every_module():
    code = ("from scripts.dev_seed import load_models; load_models(); "
            "from app.db.base import Base; print(sorted(Base.metadata.tables))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True,
                         env={**os.environ, "DATABASE_URL": "sqlite://"}).stdout
    for table in ("physical_tests", "matches"):
        assert f"'{table}'" in out
