"""Isolated tests for the staging test-subscription helper. Gate A only."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.entitlements.service import EntitlementService
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.subscriptions.db import ensure_sqlite_schema
from constitution_memorizer.subscriptions.repository import SqliteSubscriptionRepository

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "staging_test_subscriptions.py"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
PLUS = UUID("11111111-1111-4111-8111-111111111111")
PRO = UUID("22222222-2222-4222-8222-222222222222")
MAX = UUID("33333333-3333-4333-8333-333333333333")
OPERATOR = UUID("44444444-4444-4444-8444-444444444444")
DIRECT_DSN = (
    "postgresql://postgres:secret@db.tvygwasuqvtnzjyjtqrq.supabase.co:5432/postgres"
)

spec = importlib.util.spec_from_file_location("staging_test_subscriptions", SCRIPT)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)


def _allowlist() -> helper.Allowlist:
    return helper.Allowlist(
        uuids={
            "plus": str(PLUS),
            "pro": str(PRO),
            "max": str(MAX),
        },
        labels={
            "plus": "sanjisworking@gmail.com",
            "pro": "sanj.ritz@gmail.com",
            "max": "sanjali.suryawanshi192@gmail.com",
        },
        operator_uuid=str(OPERATOR),
    )


def _conn(tmp_path: Path):
    conn = open_progress_db(tmp_path / "progress.db")
    ensure_sqlite_schema(conn)
    for user_id, email in (
        (PLUS, "sanjisworking@gmail.com"),
        (PRO, "sanj.ritz@gmail.com"),
        (MAX, "sanjali.suryawanshi192@gmail.com"),
    ):
        conn.execute(
            """
            INSERT INTO user_profile (
                user_id, display_name, created_at, updated_at, email
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(user_id), email, NOW.isoformat(), NOW.isoformat(), email),
        )
    conn.commit()
    return conn


def _resolve(conn, user_id: UUID, now: datetime = NOW):
    repo = SqliteSubscriptionRepository(conn)
    service = EntitlementService(
        subscriptions=repo,
        access_store=SimpleNamespace(is_admin=lambda uid: False),
    )
    return service.resolve(user_id, now=now)


def _meta(conn, user_id: UUID) -> dict:
    row = conn.execute(
        "SELECT provider_metadata FROM user_subscription WHERE user_id = ? AND is_current = 1",
        (str(user_id),),
    ).fetchone()
    assert row is not None
    return helper.load_meta(row["provider_metadata"])


def test_helper_does_not_import_application_entitlement_or_billing() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "constitution_memorizer.entitlements" not in source
    assert "constitution_memorizer.subscriptions" not in source
    assert "constitution_memorizer.web" not in source


def test_operational_context_refuses_non_staging() -> None:
    for app_env in ("test", "development", "production", ""):
        with pytest.raises(helper.StagingTestSubscriptionError, match="APP_ENV"):
            helper.require_operational_context(
                {
                    "APP_ENV": app_env,
                    "STAGING_TEST_SUBSCRIPTIONS_ENABLED": "true",
                },
                DIRECT_DSN,
            )


def test_main_refuses_test_env_without_connecting() -> None:
    code = helper.main(
        ["apply", "--all"],
        env={
            "APP_ENV": "test",
            "STAGING_TEST_SUBSCRIPTIONS_ENABLED": "true",
            "DATABASE_URL": DIRECT_DSN,
            "STAGING_TEST_SUBSCRIPTION_UUIDS": (
                f"plus:{PLUS},pro:{PRO},max:{MAX}"
            ),
            "STAGING_TEST_SUBSCRIPTION_OPERATOR_UUID": str(OPERATOR),
        },
    )
    assert code == 2


def test_dsn_identity_exact_and_redacted() -> None:
    identity = helper.require_operational_context(
        {
            "APP_ENV": "staging",
            "STAGING_TEST_SUBSCRIPTIONS_ENABLED": "true",
        },
        DIRECT_DSN,
    )
    assert identity.host == "db.tvygwasuqvtnzjyjtqrq.supabase.co"
    assert "secret" not in str(identity)
    with pytest.raises(helper.StagingTestSubscriptionError, match="unknown"):
        helper.parse_dsn("sqlite:///tmp/progress.db")
    with pytest.raises(helper.StagingTestSubscriptionError, match="unknown"):
        helper.parse_dsn("postgres://postgres@localhost/postgres")
    with pytest.raises(helper.StagingTestSubscriptionError, match="approved"):
        helper.require_operational_context(
            {
                "APP_ENV": "staging",
                "STAGING_TEST_SUBSCRIPTIONS_ENABLED": "true",
            },
            "postgresql://postgres.tvygwasuqvtnzjyjtqrq:secret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
        )


def test_apply_all_plus_pro_max_through_resolver(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    for user_id, state in ((PLUS, "plus"), (PRO, "pro"), (MAX, "max")):
        helper.apply_on_connection(
            conn,
            allowlist=allowlist,
            user_id=str(user_id),
            state=state,
            now=NOW,
            commit=True,
        )
    plus = _resolve(conn, PLUS)
    pro = _resolve(conn, PRO)
    maxed = _resolve(conn, MAX)
    assert plus.tier == "plus" and plus.is_subscribed is True
    assert plus.can_open_playground is True
    assert plus.playground_block_reason is None
    assert plus.playground_law_limit == 10
    assert pro.tier == "pro" and pro.playground_law_limit == 30
    assert maxed.tier == "max" and maxed.playground_law_limit is None
    assert maxed.is_subscribed is True


def test_snapshots_are_not_recursive(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    helper.apply_on_connection(
        conn,
        allowlist=_allowlist(),
        user_id=str(PLUS),
        state="plus",
        now=NOW,
        commit=True,
    )
    helper.apply_on_connection(
        conn,
        allowlist=_allowlist(),
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=True,
    )
    meta = _meta(conn, PLUS)
    assert "baseline" not in meta["baseline"]
    assert "last_helper_state" not in meta["baseline"]
    assert "baseline" not in meta["last_helper_state"]
    assert "last_helper_state" not in meta["last_helper_state"]


def test_expired_and_stale_active_are_distinct(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
    )
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=True,
    )
    expired = _resolve(conn, PLUS)
    assert expired.subscription_status == "expired"
    assert expired.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    helper.restore_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), now=NOW, commit=True
    )
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="stale_active",
        now=NOW,
        commit=True,
    )
    stale = _resolve(conn, PLUS)
    assert stale.subscription_status == "active"
    assert stale.playground_block_reason == BLOCK_PAID_PERIOD_ENDED


def test_halted_keeps_future_period(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PRO), state="pro", now=NOW, commit=True
    )
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PRO), state="halted", now=NOW, commit=True
    )
    snap = _resolve(conn, PRO)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert snap.can_open_playground is False


def test_restore_is_exact_original_period(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    applied = helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(MAX), state="max", now=NOW, commit=True
    )
    original_end = applied["after"]["billing_period_end"]
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(MAX),
        state="expired",
        now=NOW,
        commit=True,
    )
    restored = helper.restore_on_connection(
        conn, allowlist=allowlist, user_id=str(MAX), now=NOW, commit=True
    )
    assert restored["after"]["status"] == "active"
    assert restored["after"]["tier"] == "max"
    assert restored["after"]["billing_period_end"] == original_end
    snap = _resolve(conn, MAX)
    assert snap.is_subscribed is True
    assert snap.tier == "max"


def test_restore_refuses_elapsed_baseline(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
    )
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=True,
    )
    later = NOW + timedelta(days=40)
    with pytest.raises(helper.StagingTestSubscriptionError, match="renew"):
        helper.restore_on_connection(
            conn, allowlist=allowlist, user_id=str(PLUS), now=later, commit=True
        )


def test_drift_aborts(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
    )
    conn.execute(
        "UPDATE user_subscription SET status = 'paused' WHERE user_id = ?",
        (str(PLUS),),
    )
    conn.commit()
    with pytest.raises(helper.StagingTestSubscriptionError, match="unexpected change"):
        helper.apply_on_connection(
            conn,
            allowlist=allowlist,
            user_id=str(PLUS),
            state="expired",
            now=NOW,
            commit=True,
        )


def test_refuses_admin_provider_and_foreign_history(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(PLUS), NOW.isoformat()),
    )
    conn.commit()
    with pytest.raises(helper.StagingTestSubscriptionError, match="admin"):
        helper.apply_on_connection(
            conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
        )
    conn.execute("DELETE FROM user_roles")
    conn.execute(
        """
        INSERT INTO user_subscription (
            id, user_id, provider, provider_subscription_id, tier, status,
            cancel_at_period_end, is_current, provider_metadata, created_at, updated_at
        ) VALUES (?, ?, 'razorpay', 'sub_real', 'plus', 'active', 0, 1, '{}', ?, ?)
        """,
        (str(uuid4()), str(PRO), NOW.isoformat(), NOW.isoformat()),
    )
    conn.commit()
    with pytest.raises(helper.StagingTestSubscriptionError, match="provider-backed"):
        helper.apply_on_connection(
            conn, allowlist=allowlist, user_id=str(PRO), state="pro", now=NOW, commit=True
        )
    stranger = UUID("55555555-5555-4555-8555-555555555555")
    with pytest.raises(helper.StagingTestSubscriptionError, match="allowlisted"):
        helper.apply_on_connection(
            conn,
            allowlist=allowlist,
            user_id=str(stranger),
            state="plus",
            now=NOW,
            commit=True,
        )


def test_reset_deletes_helper_row_keeps_audit_and_resolves_free(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
    )
    helper.apply_on_connection(
        conn,
        allowlist=allowlist,
        user_id=str(PLUS),
        state="expired",
        now=NOW,
        commit=True,
    )
    helper.reset_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), now=NOW, commit=True
    )
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM user_subscription WHERE user_id = ?",
        (str(PLUS),),
    ).fetchone()["n"]
    assert remaining == 0
    audits = conn.execute(
        "SELECT COUNT(*) AS n FROM admin_audit_log WHERE target_user_id = ?",
        (str(PLUS),),
    ).fetchone()["n"]
    assert audits >= 2
    snap = _resolve(conn, PLUS)
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.admin_override is False
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED


def test_reset_refuses_when_charges_exist(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    allowlist = _allowlist()
    applied = helper.apply_on_connection(
        conn, allowlist=allowlist, user_id=str(PLUS), state="plus", now=NOW, commit=True
    )
    conn.execute(
        """
        INSERT INTO subscription_charge (
            id, provider, provider_payment_id, user_subscription_id,
            amount_refunded_paise, access_effect, created_at, updated_at
        ) VALUES (?, 'razorpay', 'pay_x', ?, 0, 'none', ?, ?)
        """,
        (str(uuid4()), applied["row_id"], NOW.isoformat(), NOW.isoformat()),
    )
    conn.commit()
    with pytest.raises(helper.StagingTestSubscriptionError, match="subscription_charge"):
        helper.reset_on_connection(
            conn, allowlist=allowlist, user_id=str(PLUS), now=NOW, commit=True
        )


def test_inventory_does_not_delete(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    conn.execute(
        """
        CREATE TABLE user_device (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO user_device (id, user_id) VALUES (?, ?)",
        (str(uuid4()), str(PLUS)),
    )
    conn.commit()
    result = helper.inventory_on_connection(conn, str(PLUS))
    assert result["counts"]["user_device"] == 1
    still = conn.execute("SELECT COUNT(*) AS n FROM user_device").fetchone()["n"]
    assert still == 1


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    helper.apply_on_connection(
        conn,
        allowlist=_allowlist(),
        user_id=str(PLUS),
        state="plus",
        now=NOW,
        commit=False,
    )
    count = conn.execute("SELECT COUNT(*) AS n FROM user_subscription").fetchone()["n"]
    assert count == 0


def test_inspect_email(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    found = helper.inspect_on_connection(conn, email="sanjisworking@gmail.com")
    assert found["user_id"] == str(PLUS)
    assert found["admin"] is False
