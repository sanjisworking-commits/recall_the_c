#!/usr/bin/env python3
"""WS8 disposable PostgreSQL EXPLAIN (ANALYZE, BUFFERS) CLI (T15).

Thin operator wrapper around playground.benchmarking. Requires a newly
created local disposable postgresql:// URL. Never uses process
DATABASE_URL. Same guard and execution path as
``scripts/benchmark_playground.py --explain``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from constitution_memorizer.playground.benchmarking import run_cli


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--explain" not in args:
        args = ["--explain", *args]
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
