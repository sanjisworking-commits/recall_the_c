"""Isolated PostgreSQL proof for the staging test-subscription helper.

Starts a disposable cluster on 127.0.0.1. Does not read DATABASE_URL and
refuses any non-loopback target. CI without PostgreSQL binaries skips.
"""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "staging_test_subscriptions.py"
PGBIN = Path("/usr/lib/postgresql/16/bin")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PLUS = UUID("11111111-1111-4111-8111-111111111111")
PRO = UUID("22222222-2222-4222-8222-222222222222")
MAX = UUID("33333333-3333-4333-8333-333333333333")
OPERATOR = UUID("44444444-4444-4444-8444-444444444444")

spec = importlib.util.spec_from_file_location("staging_test_subscriptions", SCRIPT)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)

SCHEMA = """
CREATE TABLE user_profile (
    user_id UUID PRIMARY KEY,
    display_name TEXT,
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin')),
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, role)
);
CREATE TABLE user_subscription (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('razorpay')),
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    provider_plan_id TEXT,
    tier TEXT NOT NULL CHECK (tier IN ('plus', 'pro', 'max')),
    status TEXT NOT NULL CHECK (status IN (
        'created', 'authenticated', 'active', 'pending', 'halted',
        'paused', 'cancelled', 'completed', 'expired'
    )),
    billing_period_start TIMESTAMPTZ,
    billing_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX user_subscription_one_current
    ON user_subscription (user_id) WHERE is_current;
CREATE TABLE subscription_charge (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('razorpay')),
    provider_payment_id TEXT NOT NULL,
    user_subscription_id UUID,
    amount_refunded_paise INTEGER NOT NULL DEFAULT 0,
    access_effect TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID NOT NULL,
    action TEXT NOT NULL,
    target_user_id UUID,
    target_type TEXT,
    target_id TEXT,
    before_state JSONB,
    after_state JSONB,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _allowlist() -> helper.Allowlist:
    return helper.Allowlist(
        uuids={"plus": str(PLUS), "pro": str(PRO), "max": str(MAX)},
        labels={
            "plus": "sanjisworking@gmail.com",
            "pro": "sanj.ritz@gmail.com",
            "max": "sanjali.suryawanshi192@gmail.com",
        },
        operator_uuid=str(OPERATOR),
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def postgres_url() -> str:
    initdb = PGBIN / "initdb"
    pg_ctl = PGBIN / "pg_ctl"
    if not initdb.exists() or not pg_ctl.exists():
        pytest.skip("isolated PostgreSQL binaries are not installed")
    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="staging-helper-pg-") as tmp:
        root = Path(tmp)
        data = root / "data"
        log = root / "server.log"
        subprocess.run(
            [str(initdb), "-D", str(data), "-U", "postgres", "--auth=trust", "--no-sync"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                str(pg_ctl),
                "-D",
                str(data),
                "-l",
                str(log),
                "-o",
                f"-k {root} -p {port} -c listen_addresses=127.0.0.1",
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        url = f"postgresql://postgres@127.0.0.1:{port}/postgres"
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                info = conn.info
                if info.host not in {"127.0.0.1", "localhost"}:
                    raise RuntimeError("isolated postgres is not loopback")
                with conn.cursor() as cur:
                    cur.execute(SCHEMA)
                    for user_id, email in (
                        (PLUS, "sanjisworking@gmail.com"),
                        (PRO, "sanj.ritz@gmail.com"),
                        (MAX, "sanjali.suryawanshi192@gmail.com"),
                    ):
                        cur.execute(
                            """
                            INSERT INTO user_profile (
                                user_id, display_name, email, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s)
                            """,
                            (user_id, email, email, NOW, NOW),
                        )
            yield url
        finally:
            subprocess.run(
                [str(pg_ctl), "-D", str(data), "stop", "-m", "fast"],
                check=False,
                capture_output=True,
                text=True,
            )


@pytest.fixture
def conn(postgres_url: str):
    import psycopg

    target = helper.parse_target(
        postgres_url.replace("postgresql://postgres@", "postgresql://postgres:unused@")
    )
    assert target.host == "127.0.0.1"
    assert "tvygwasuqvtnzjyjtqrq" not in postgres_url
    connection = psycopg.connect(postgres_url)
    try:
        yield connection
    finally:
        connection.close()


def _count(conn, user_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM user_subscription WHERE user_id = %s",
            (user_id,),
        )
        return int(cur.fetchone()[0])


def test_isolated_postgres_dry_run_round_trip_and_exact_reset(conn) -> None:
    allowlist = _allowlist()
    proposed = helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="plus",
        now=NOW,
        commit=False,
        postgres=True,
    )
    assert proposed["before"] is None
    assert proposed["after"]["tier"] == "plus"
    assert proposed["after"]["status"] == "active"
    assert _count(conn, PLUS) == 0

    applied = helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="plus",
        now=NOW,
        commit=True,
        postgres=True,
    )
    again = helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="plus",
        now=NOW,
        commit=True,
        postgres=True,
    )
    assert again["result"] == "unchanged"
    assert again["before"]["billing_period_end"] == applied["after"]["billing_period_end"]

    dry_expired = helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=False,
        postgres=True,
    )
    assert dry_expired["before"]["status"] == "active"
    assert dry_expired["after"]["status"] == "expired"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM user_subscription WHERE user_id = %s",
            (PLUS,),
        )
        assert cur.fetchone()[0] == "active"

    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PRO),
        state="pro",
        now=NOW,
        commit=True,
        postgres=True,
    )
    original_end = applied["after"]["billing_period_end"]
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=True,
        postgres=True,
    )
    restored = helper.restore_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        now=NOW,
        commit=True,
        postgres=True,
    )
    assert restored["after"]["status"] == "active"
    assert restored["after"]["billing_period_end"] == original_end

    dry_reset = helper.reset_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        now=NOW,
        commit=False,
        postgres=True,
    )
    assert dry_reset["row_ids"] == [applied["row_id"]]
    assert _count(conn, PLUS) == 1

    helper.reset_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        now=NOW,
        commit=True,
        postgres=True,
    )
    assert _count(conn, PLUS) == 0
    assert _count(conn, PRO) == 1
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM admin_audit_log
            WHERE target_user_id = %s AND action = %s
            """,
            (PLUS, helper.AUDIT_RESET),
        )
        assert int(cur.fetchone()[0]) == 1

    found = helper.inspect_on_connection(
        conn, email="sanj.ritz@gmail.com", postgres=True
    )
    assert found["user_id"] == str(PRO)
    assert found["eligible"] is True
    assert found["admin"] is False


def test_isolated_postgres_reset_refuses_charges_and_keeps_row(conn) -> None:
    allowlist = _allowlist()
    applied = helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(MAX),
        state="max",
        now=NOW,
        commit=True,
        postgres=True,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscription_charge (
                id, provider, provider_payment_id, user_subscription_id
            ) VALUES (%s, 'razorpay', 'pay_isolated', %s)
            """,
            (uuid4(), applied["row_id"]),
        )
        conn.commit()
    with pytest.raises(helper.StagingTestSubscriptionError, match="subscription_charge"):
        helper.reset_on_connection(
            conn,
            allowlist=allowlist,
            user_id=str(MAX),
            now=NOW,
            commit=True,
            postgres=True,
        )
    assert _count(conn, MAX) == 1
