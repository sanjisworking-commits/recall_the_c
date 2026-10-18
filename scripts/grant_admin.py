"""Grant the admin role to a user (CLI-only until admin accounts have MFA).

Inserts a user_roles row and writes the audit log in the same transaction.
Never creates a subscription or touches billing state — the admin's full
Recall entitlement follows the role row itself.

Playground paywall bypass for listed Google emails also follows
ADMIN_EMAILS (default sanjisworking@gmail.com) without this CLI. That
allowlist does not grant the /admin console.

    # Hosted (DATABASE_URL from .env)
    .venv/bin/python scripts/grant_admin.py --email name@recall.app
    .venv/bin/python scripts/grant_admin.py --user-id <uuid>

    # Local SQLite (dev)
    .venv/bin/python scripts/grant_admin.py --sqlite data/progress/progress.db --user-id <uuid>

Fallback for the Supabase SQL editor:

    INSERT INTO user_roles (user_id, role) VALUES ('<uuid>', 'admin');
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _audit_states(user_id: str) -> tuple[str, str]:
    return (
        json.dumps({"role": None}),
        json.dumps({"role": "admin", "user_id": user_id}),
    )


def _resolve_email_pg(cur, email: str) -> str | None:
    cur.execute(
        "SELECT user_id FROM user_profile WHERE LOWER(email) = LOWER(%s)",
        (email,),
    )
    row = cur.fetchone()
    return str(row[0]) if row else None


def _grant_postgres(database_url: str, user_id: str | None, email: str | None) -> int:
    import psycopg

    url = database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            if user_id is None:
                assert email is not None
                user_id = _resolve_email_pg(cur, email)
                if user_id is None:
                    print(
                        f"No user_profile row with email {email!r}. Use "
                        "--user-id with the UUID from the Supabase dashboard."
                    )
                    return 1
            cur.execute(
                "SELECT COUNT(*) FROM user_roles WHERE role = 'admin'"
            )
            first_admin = int(cur.fetchone()[0]) == 0
            cur.execute(
                """
                INSERT INTO user_roles (user_id, role, created_at, created_by)
                VALUES (%s, 'admin', NOW(), NULL)
                ON CONFLICT DO NOTHING
                """,
                (user_id,),
            )
            if cur.rowcount == 0:
                print(f"{user_id} is already an administrator; nothing to do.")
                conn.rollback()
                return 0
            before, after = _audit_states(user_id)
            cur.execute(
                """
                INSERT INTO admin_audit_log (
                    admin_user_id, action, target_user_id, target_type,
                    target_id, before_state, after_state, reason, created_at
                ) VALUES (%s, %s, %s, 'user_role', %s, %s, %s, %s, NOW())
                """,
                (
                    user_id,
                    "bootstrap_admin" if first_admin else "grant_admin_role",
                    user_id,
                    user_id,
                    before,
                    after,
                    "CLI grant_admin.py",
                ),
            )
        conn.commit()
    print(f"Granted admin to {user_id} (audit row written).")
    return 0


def _grant_sqlite(db_path: Path, user_id: str | None, email: str | None) -> int:
    from constitution_memorizer.progress.db import open_progress_db

    conn = open_progress_db(db_path)
    try:
        if user_id is None:
            assert email is not None
            row = conn.execute(
                "SELECT user_id FROM user_profile WHERE LOWER(email) = LOWER(?)",
                (email,),
            ).fetchone()
            if row is None:
                print(f"No user_profile row with email {email!r}.")
                return 1
            user_id = str(row["user_id"])
        first_admin = (
            conn.execute(
                "SELECT COUNT(*) AS n FROM user_roles WHERE role = 'admin'"
            ).fetchone()["n"]
            == 0
        )
        cur = conn.execute(
            """
            INSERT INTO user_roles (user_id, role, created_at, created_by)
            VALUES (?, 'admin', ?, NULL)
            ON CONFLICT DO NOTHING
            """,
            (user_id, _now_iso()),
        )
        if cur.rowcount == 0:
            print(f"{user_id} is already an administrator; nothing to do.")
            return 0
        before, after = _audit_states(user_id)
        conn.execute(
            """
            INSERT INTO admin_audit_log (
                id, admin_user_id, action, target_user_id, target_type,
                target_id, before_state, after_state, reason, created_at
            ) VALUES (?, ?, ?, ?, 'user_role', ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                "bootstrap_admin" if first_admin else "grant_admin_role",
                user_id,
                user_id,
                before,
                after,
                "CLI grant_admin.py",
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Granted admin to {user_id} (audit row written).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--user-id", help="Supabase user UUID")
    who.add_argument("--email", help="Email from the identity directory")
    parser.add_argument(
        "--sqlite",
        metavar="DB_PATH",
        help="Use a local SQLite progress DB instead of DATABASE_URL",
    )
    args = parser.parse_args()

    if args.user_id is not None:
        try:
            uuid.UUID(args.user_id)
        except ValueError:
            print(f"Not a UUID: {args.user_id!r}")
            return 1

    if args.sqlite:
        return _grant_sqlite(Path(args.sqlite), args.user_id, args.email)

    from constitution_memorizer.multiuser.settings import (
        get_multiuser_settings,
        load_env_file,
    )

    load_env_file()
    database_url = (get_multiuser_settings().database_url or "").strip()
    if not database_url.startswith("postgresql"):
        print(
            "DATABASE_URL is not a PostgreSQL URL. For local SQLite use "
            "--sqlite data/progress/progress.db"
        )
        return 1
    return _grant_postgres(database_url, args.user_id, args.email)


if __name__ == "__main__":
    raise SystemExit(main())
