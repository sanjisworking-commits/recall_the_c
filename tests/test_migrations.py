"""Guard: every Alembic revision parses and the graph has one head."""

from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"
EXPECTED_HEAD = "20261103_0028"  # B1 (2026-11-03): 0028 adds the permanent-choice ledger; earlier revisions unchanged.


def test_every_migration_file_parses():
    files = sorted(VERSIONS.glob("*.py"))
    assert files, "expected alembic/versions/*.py"
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_alembic_has_exactly_one_head():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [EXPECTED_HEAD], heads
