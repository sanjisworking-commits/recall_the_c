#!/usr/bin/env python3
"""Playground WS6 benchmark CLI. See playground/benchmarking.py.

Not part of the default pytest run. Fail-closed: never uses process
DATABASE_URL, never writes a nonempty SQLite file, never runs EXPLAIN (T15).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from constitution_memorizer.playground.benchmarking import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
