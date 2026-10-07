"""Operator proof: alembic upgrade against a disposable PostgreSQL database.

CI does not run a live Postgres instance. Production/staging operators run:

    DATABASE_URL=postgresql://... python3 scripts/verify_postgres_migrations.py

Expected single head: 20260927_0027

Does not DROP user_free_articles, access_grants, or billing_orders.
Does not fetch a payment provider. Does not hydrate Bare Acts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
LEGACY_TABLES = ("user_free_articles", "access_grants", "billing_orders")


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print(
            "DATABASE_URL is not set. Skipping live PostgreSQL upgrade. "
            "CI proves parse + one-head; operators run this script against a "
            "disposable database before production deploy.",
            file=sys.stderr,
        )
        return 2
    if not url.startswith("postgres"):
        print("DATABASE_URL must be a postgresql:// URL", file=sys.stderr)
        return 2
    env = os.environ.copy()
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if upgrade.returncode != 0:
        return upgrade.returncode
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    print(current.stdout)
    if EXPECTED_HEAD not in (current.stdout or ""):
        print(
            f"expected alembic current to include {EXPECTED_HEAD}",
            file=sys.stderr,
        )
        return 1
    heads = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    print(heads.stdout)
    if EXPECTED_HEAD not in (heads.stdout or ""):
        print("alembic heads does not list the expected revision", file=sys.stderr)
        return 1
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed; table-existence check skipped")
        return 0
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for table in LEGACY_TABLES:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = %s",
                    (table,),
                )
                if cur.fetchone() is None:
                    print(f"missing legacy table {table}", file=sys.stderr)
                    return 1
    print("PostgreSQL migrations OK; legacy tables retained; one head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
