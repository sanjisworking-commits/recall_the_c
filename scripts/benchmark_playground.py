#!/usr/bin/env python3
"""Playground WS6/WS7/WS8/WS10/WS11 benchmark CLI. See playground/benchmarking.py.

Not part of the default pytest run. Fail-closed: never uses process
DATABASE_URL, never writes a nonempty SQLite file.
Omit --protocol for the T13 unlabeled runner. --protocol bnss-cold-warm is
the T14 BNSS cold/warm Bare Act protocol. --explain is the T15 disposable
PostgreSQL EXPLAIN (ANALYZE, BUFFERS) path and is not the HTTP runner.
--concurrency is the T18 read-only overlap harness (1/5/10/25, SQLite-only,
not default pytest). --mutations and --webhooks are T19 (SQLite-only
service-level races and process_delivery duplicates, not default pytest,
no live Razorpay). --page-weight is T20 (SQLite-only in-process ASGI + disk
+ gzip equivalents, not Lighthouse, not default pytest, no external
network). --cold-start is T21 (SQLite-only fresh-interpreter import and
create_app hydration guard, not default pytest, no startup SLA).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from constitution_memorizer.playground.benchmarking import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
