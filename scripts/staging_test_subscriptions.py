"""Operator CLI for staging test subscriptions. Gate A: local/isolated use.

These rows are ordinary user_subscription records for designated test
accounts. They are not purchases and do not prove billing.

Operational ``main()`` refuses every APP_ENV except staging and refuses
any DSN that is not an exact approved staging identity. ``inspect``
discovers UUIDs without a pre-existing UUID allowlist. Dry-run reads
those rows and does not write. Local tests call ``apply_on_connection``
on an injected connection; they do not make ``APP_ENV=test`` a valid
operational environment.

Never print credentials or the raw DSN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import parse_qsl, unquote, urlparse

TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
COHORTS = ("plus", "pro", "max")
STABLE_STATES = frozenset(COHORTS)
TEMPORARY_STATES = frozenset({"expired", "halted", "stale_active"})
APPLY_STATES = STABLE_STATES | TEMPORARY_STATES
SNAPSHOT_KEYS = frozenset({"baseline", "last_helper_state"})
AUDIT_APPLY = "staging_test_subscription_apply"
AUDIT_RESTORE = "staging_test_subscription_restore"
AUDIT_RENEW = "staging_test_subscription_renew"
AUDIT_RESET = "staging_test_subscription_reset"
DIRECT_STAGING = (
    ("db.tvygwasuqvtnzjyjtqrq.supabase.co", 5432, "postgres", "postgres"),
)
ALLOWED_SSLMODES = frozenset({"prefer", "require", "verify-ca", "verify-full"})
# Unspecified libpq parameters fall through to the process environment.
# Scrub these around connect so PGHOSTADDR and the rest cannot retarget it.
LIBPQ_OVERRIDE_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGOPTIONS",
    "PGSSLMODE",
    "PGREQUIRESSL",
    "PGSSLROOTCERT",
    "PGSSLCERT",
    "PGSSLKEY",
    "PGCHANNELBINDING",
    "PGAPPNAME",
    "PGTARGETSESSIONATTRS",
)


class StagingTestSubscriptionError(Exception):
    """Fail-closed operator or mutation error. Safe to print."""


@dataclass(frozen=True)
class DsnIdentity:
    host: str
    port: int
    database: str
    user: str


@dataclass(frozen=True)
class ApprovedTarget:
    """Parsed connection target. ``repr`` omits the password."""

    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str | None

    def identity(self) -> DsnIdentity:
        return DsnIdentity(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
        )

    def __repr__(self) -> str:
        mode = f", sslmode={self.sslmode!r}" if self.sslmode else ""
        return (
            f"ApprovedTarget(host={self.host!r}, port={self.port}, "
            f"database={self.database!r}, user={self.user!r}{mode})"
        )


@dataclass(frozen=True)
class Allowlist:
    uuids: dict[str, str]
    labels: dict[str, str]
    operator_uuid: str

    def cohort_for(self, user_id: str) -> str:
        for cohort, mapped in self.uuids.items():
            if mapped == user_id:
                return cohort
        raise StagingTestSubscriptionError("account UUID is not allowlisted")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return as_utc(value).replace(microsecond=0).isoformat()
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    return as_utc(parsed).replace(microsecond=0).isoformat()


def parse_dt(value: Any) -> datetime | None:
    stamp = iso(value)
    if stamp is None:
        return None
    return datetime.fromisoformat(stamp)


def _sslmode_from_query(query: str) -> str | None:
    if not query:
        return None
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise StagingTestSubscriptionError(
            "connection parameter override is not allowed"
        ) from exc
    if len(pairs) != 1 or pairs[0][0].lower() != "sslmode":
        raise StagingTestSubscriptionError(
            "connection parameter override is not allowed"
        )
    mode = pairs[0][1].strip().lower()
    if mode not in ALLOWED_SSLMODES:
        raise StagingTestSubscriptionError(
            "connection parameter override is not allowed"
        )
    return mode


def parse_target(url: str) -> ApprovedTarget:
    """Parse a URL into host/port/database/user plus a non-logged password.

    Query parameters other than a strengthening ``sslmode`` are rejected.
    libpq would otherwise let ``?host=`` or ``?hostaddr=`` replace the host
    that the authority section appears to name.
    """
    raw = (url or "").strip()
    if not raw or any(ch.isspace() for ch in raw):
        raise StagingTestSubscriptionError("unknown connection format")
    if raw.startswith("postgresql+psycopg://"):
        raw = "postgresql://" + raw[len("postgresql+psycopg://") :]
    if "#" in raw or raw.startswith("postgres://"):
        raise StagingTestSubscriptionError("unknown connection format")
    parsed = urlparse(raw)
    if parsed.scheme != "postgresql" or not parsed.hostname or parsed.fragment:
        raise StagingTestSubscriptionError("unknown connection format")
    if "," in (parsed.netloc or ""):
        raise StagingTestSubscriptionError(
            "connection parameter override is not allowed"
        )
    database = (parsed.path or "").lstrip("/")
    if not database or "/" in database:
        raise StagingTestSubscriptionError("unknown connection format")
    user = unquote(parsed.username or "")
    if not user:
        raise StagingTestSubscriptionError("unknown connection format")
    password = unquote(parsed.password or "")
    if password == "":
        raise StagingTestSubscriptionError(
            "connection password must be in the URL"
        )
    port = parsed.port if parsed.port is not None else 5432
    return ApprovedTarget(
        host=parsed.hostname.lower(),
        port=int(port),
        database=database,
        user=user,
        password=password,
        sslmode=_sslmode_from_query(parsed.query),
    )


def parse_dsn(url: str) -> DsnIdentity:
    return parse_target(url).identity()


def _approved_candidate(target: ApprovedTarget) -> tuple[str, int, str, str]:
    return (target.host, target.port, target.database, target.user)


def require_operational_context(
    env: Mapping[str, str], dsn: str
) -> DsnIdentity:
    app_env = (env.get("APP_ENV") or "").strip()
    if app_env != "staging":
        raise StagingTestSubscriptionError("APP_ENV must be staging")
    flag = (env.get("STAGING_TEST_SUBSCRIPTIONS_ENABLED") or "").strip().lower()
    if flag not in TRUE_TOKENS:
        raise StagingTestSubscriptionError(
            "STAGING_TEST_SUBSCRIPTIONS_ENABLED is off"
        )
    if not (dsn or "").strip():
        raise StagingTestSubscriptionError("DATABASE_URL is not set")
    target = parse_target(dsn)
    if _approved_candidate(target) not in tuple(DIRECT_STAGING):
        raise StagingTestSubscriptionError(
            "database identity is not the approved staging target"
        )
    return target.identity()


def parse_cohort_map(raw: str, *, kind: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    text = (raw or "").strip()
    if not text:
        raise StagingTestSubscriptionError(f"{kind} is empty")
    for part in text.split(","):
        if ":" not in part:
            raise StagingTestSubscriptionError(f"invalid {kind} entry")
        cohort, value = part.split(":", 1)
        cohort = cohort.strip().lower()
        value = value.strip()
        if cohort not in COHORTS or not value:
            raise StagingTestSubscriptionError(f"invalid {kind} entry")
        if cohort in mapping:
            raise StagingTestSubscriptionError(f"duplicate {kind} cohort")
        mapping[cohort] = value
    if set(mapping) != set(COHORTS):
        raise StagingTestSubscriptionError(f"{kind} must include plus, pro, max")
    return mapping


def load_allowlist(env: Mapping[str, str]) -> Allowlist:
    uuids = parse_cohort_map(
        env.get("STAGING_TEST_SUBSCRIPTION_UUIDS") or "",
        kind="STAGING_TEST_SUBSCRIPTION_UUIDS",
    )
    for cohort, value in uuids.items():
        try:
            parsed = str(uuid.UUID(value))
        except ValueError as exc:
            raise StagingTestSubscriptionError(
                f"invalid UUID for {cohort}"
            ) from exc
        uuids[cohort] = parsed
    labels_raw = (env.get("STAGING_TEST_SUBSCRIPTION_LABELS") or "").strip()
    labels = (
        parse_cohort_map(labels_raw, kind="STAGING_TEST_SUBSCRIPTION_LABELS")
        if labels_raw
        else {cohort: "" for cohort in COHORTS}
    )
    operator = (env.get("STAGING_TEST_SUBSCRIPTION_OPERATOR_UUID") or "").strip()
    try:
        operator_uuid = str(uuid.UUID(operator))
    except ValueError as exc:
        raise StagingTestSubscriptionError(
            "STAGING_TEST_SUBSCRIPTION_OPERATOR_UUID is required"
        ) from exc
    return Allowlist(uuids=uuids, labels=labels, operator_uuid=operator_uuid)


def period_for(state: str, now: datetime) -> tuple[datetime, datetime]:
    clock = as_utc(now).replace(microsecond=0)
    if state in STABLE_STATES or state == "halted":
        return clock - timedelta(days=1), clock + timedelta(days=28)
    if state in {"expired", "stale_active"}:
        return clock - timedelta(days=40), clock - timedelta(days=1)
    raise StagingTestSubscriptionError(f"unknown state {state!r}")


def status_for(state: str) -> str:
    if state in STABLE_STATES or state == "stale_active":
        return "active"
    if state == "expired":
        return "expired"
    if state == "halted":
        return "halted"
    raise StagingTestSubscriptionError(f"unknown state {state!r}")


def strip_snapshots(meta: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dict(meta).items() if key not in SNAPSHOT_KEYS}


def load_meta(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(str(raw))


def row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def snapshot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    meta = load_meta(row.get("provider_metadata"))
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "provider": str(row["provider"]),
        "provider_customer_id": row.get("provider_customer_id"),
        "provider_subscription_id": row.get("provider_subscription_id"),
        "provider_plan_id": row.get("provider_plan_id"),
        "tier": str(row["tier"]),
        "status": str(row["status"]),
        "billing_period_start": iso(row.get("billing_period_start")),
        "billing_period_end": iso(row.get("billing_period_end")),
        "cancel_at_period_end": bool(row.get("cancel_at_period_end")),
        "is_current": bool(row.get("is_current")),
        "created_at": iso(row.get("created_at")),
        "helper_meta": strip_snapshots(meta),
    }


def comparable(row: Mapping[str, Any]) -> dict[str, Any]:
    return snapshot_row(row)


def helper_owned(row: Mapping[str, Any]) -> bool:
    meta = load_meta(row.get("provider_metadata"))
    return bool(meta.get("staging_test_subscription")) and not row.get(
        "provider_subscription_id"
    )


class Store:
    def __init__(self, conn: Any, *, postgres: bool = False) -> None:
        self.conn = conn
        self.postgres = postgres
        self._pg_cur: Any = None
        self._tx_open = False
        if postgres:
            from psycopg.rows import dict_row

            # Explicit BEGIN/COMMIT. Autocommit avoids an implicit transaction
            # that would make a leading BEGIN a no-op.
            conn.autocommit = True
            self._pg_cur = conn.cursor(row_factory=dict_row)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        query = sql if self.postgres else sql.replace("%s", "?")
        if self.postgres:
            assert self._pg_cur is not None
            self._pg_cur.execute(query, params)
            return self._pg_cur
        return self.conn.execute(query, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return row_dict(row)

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cur = self.execute(sql, params)
        return [row_dict(row) for row in cur.fetchall()]

    def dump_meta(self, meta: Mapping[str, Any]) -> Any:
        payload = dict(meta)
        if self.postgres:
            from psycopg.types.json import Json

            return Json(payload)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def sql_bool(self, value: bool) -> Any:
        if self.postgres:
            return bool(value)
        return 1 if value else 0

    def sql_dt(self, value: datetime | None) -> Any:
        if value is None:
            return None
        clock = as_utc(value).replace(microsecond=0)
        if self.postgres:
            return clock
        return clock.isoformat()

    def begin(self) -> None:
        if self.postgres:
            self.execute("BEGIN")
            self._tx_open = True
            return
        self.execute("BEGIN IMMEDIATE")

    def begin_read_only(self) -> None:
        """Read transaction so a dry-run write fails instead of autocommitting."""
        if self.postgres:
            self.execute("BEGIN READ ONLY")
            self._tx_open = True
            return
        self.execute("BEGIN")

    def commit(self) -> None:
        if self.postgres:
            self.execute("COMMIT")
            self._tx_open = False
            return
        self.conn.commit()

    def rollback(self) -> None:
        if self.postgres:
            if self._tx_open:
                self.execute("ROLLBACK")
                self._tx_open = False
            return
        self.conn.rollback()

    def table_exists(self, name: str) -> bool:
        if self.postgres:
            row = self.fetchone(
                """
                SELECT 1 AS ok
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
                """,
                (name,),
            )
        else:
            row = self.fetchone(
                "SELECT 1 AS ok FROM sqlite_master WHERE type = 'table' AND name = %s",
                (name,),
            )
        return row is not None

    def lock_current(self, user_id: str) -> dict[str, Any] | None:
        if self.postgres:
            return self.fetchone(
                """
                SELECT * FROM user_subscription
                WHERE user_id = %s AND is_current IS TRUE
                FOR UPDATE
                """,
                (user_id,),
            )
        return self.fetchone(
            """
            SELECT * FROM user_subscription
            WHERE user_id = %s AND is_current = 1
            """,
            (user_id,),
        )


def _is_admin(store: Store, user_id: str) -> bool:
    if not store.table_exists("user_roles"):
        return False
    row = store.fetchone(
        "SELECT 1 AS ok FROM user_roles WHERE user_id = %s AND role = 'admin'",
        (user_id,),
    )
    return row is not None


def _charge_count(store: Store, subscription_id: str) -> int:
    if not store.table_exists("subscription_charge"):
        return 0
    row = store.fetchone(
        "SELECT COUNT(*) AS n FROM subscription_charge WHERE user_subscription_id = %s",
        (subscription_id,),
    )
    return int(row["n"]) if row is not None else 0


def _history(
    store: Store, user_id: str, *, lock: bool = False
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM user_subscription WHERE user_id = %s ORDER BY created_at"
    if lock and store.postgres:
        sql += " FOR UPDATE"
    return store.fetchall(sql, (user_id,))


def _select_current(
    store: Store, user_id: str, *, lock: bool
) -> dict[str, Any] | None:
    if lock:
        return store.lock_current(user_id)
    if store.postgres:
        return store.fetchone(
            """
            SELECT * FROM user_subscription
            WHERE user_id = %s AND is_current IS TRUE
            """,
            (user_id,),
        )
    return store.fetchone(
        """
        SELECT * FROM user_subscription
        WHERE user_id = %s AND is_current = 1
        """,
        (user_id,),
    )


def _require_clean_or_helper(
    store: Store,
    user_id: str,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if _is_admin(store, user_id):
        raise StagingTestSubscriptionError("account has admin role")
    if rows is None:
        rows = _history(store, user_id)
    current = None
    for row in rows:
        if row.get("provider_subscription_id"):
            raise StagingTestSubscriptionError("provider-backed subscription present")
        if not helper_owned(row):
            raise StagingTestSubscriptionError("unrelated subscription history present")
        if bool(row.get("is_current")):
            current = row
    return current


def _assert_no_drift(row: Mapping[str, Any]) -> None:
    meta = load_meta(row.get("provider_metadata"))
    expected = meta.get("last_helper_state")
    if not isinstance(expected, dict):
        raise StagingTestSubscriptionError("missing last helper state")
    live = comparable(row)
    if live != expected:
        raise StagingTestSubscriptionError("unexpected change since last helper state")


def _write_audit(
    store: Store,
    *,
    operator_uuid: str,
    action: str,
    user_id: str,
    target_id: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    reason: str,
    now: datetime,
) -> None:
    if not store.table_exists("admin_audit_log"):
        raise StagingTestSubscriptionError("admin_audit_log is missing")
    if store.postgres:
        store.execute(
            """
            INSERT INTO admin_audit_log (
                admin_user_id, action, target_user_id, target_type, target_id,
                before_state, after_state, reason, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                operator_uuid,
                action,
                user_id,
                "user_subscription",
                target_id,
                json.dumps(before, sort_keys=True) if before is not None else None,
                json.dumps(after, sort_keys=True) if after is not None else None,
                reason,
                store.sql_dt(now),
            ),
        )
        return
    store.execute(
        """
        INSERT INTO admin_audit_log (
            id, admin_user_id, action, target_user_id, target_type, target_id,
            before_state, after_state, reason, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(uuid.uuid4()),
            operator_uuid,
            action,
            user_id,
            "user_subscription",
            target_id,
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True) if after is not None else None,
            reason,
            iso(now),
        ),
    )


def _helper_meta(
    *,
    recorded_state: str,
    fixture: str,
    run_id: str,
    baseline: dict[str, Any],
    last_helper_state: dict[str, Any],
) -> dict[str, Any]:
    if "baseline" in baseline or "last_helper_state" in baseline:
        raise StagingTestSubscriptionError("baseline snapshot is nested")
    if "baseline" in last_helper_state or "last_helper_state" in last_helper_state:
        raise StagingTestSubscriptionError("last helper state is nested")
    return {
        "staging_test_subscription": True,
        "recorded_state": recorded_state,
        "fixture": fixture,
        "run_id": run_id,
        "baseline": baseline,
        "last_helper_state": last_helper_state,
    }


def inspect_on_connection(conn: Any, *, email: str, postgres: bool = False) -> dict[str, Any]:
    store = Store(conn, postgres=postgres)
    row = store.fetchone(
        "SELECT user_id, email FROM user_profile WHERE LOWER(email) = LOWER(%s)",
        (email,),
    )
    if row is None:
        raise StagingTestSubscriptionError("no user_profile for email")
    user_id = str(row["user_id"])
    current = store.fetchone(
        "SELECT * FROM user_subscription WHERE user_id = %s AND is_current = 1"
        if not postgres
        else "SELECT * FROM user_subscription WHERE user_id = %s AND is_current IS TRUE",
        (user_id,),
    )
    history = _history(store, user_id)
    try:
        _require_clean_or_helper(store, user_id, history)
    except StagingTestSubscriptionError as exc:
        eligible = False
        reason: str | None = str(exc)
    else:
        eligible = True
        reason = None
    return {
        "email": row["email"],
        "user_id": user_id,
        "admin": _is_admin(store, user_id),
        "current": snapshot_row(current) if current is not None else None,
        "history_count": len(history),
        "eligible": eligible,
        "ineligible_reason": reason,
    }


def inventory_on_connection(
    conn: Any, user_id: str, *, postgres: bool = False
) -> dict[str, Any]:
    store = Store(conn, postgres=postgres)
    counts: dict[str, int] = {}
    queries = {
        "user_device": "SELECT COUNT(*) AS n FROM user_device WHERE user_id = %s",
        "user_playground_roster_item": (
            "SELECT COUNT(*) AS n FROM user_playground_roster_item WHERE user_id = %s"
        ),
        "user_playground_mode_progress": (
            "SELECT COUNT(*) AS n FROM user_playground_mode_progress WHERE user_id = %s"
        ),
        "user_playground_revision_mode_progress": (
            "SELECT COUNT(*) AS n FROM user_playground_revision_mode_progress WHERE user_id = %s"
        ),
    }
    for table, sql in queries.items():
        if store.table_exists(table):
            row = store.fetchone(sql, (user_id,))
            counts[table] = int(row["n"]) if row is not None else 0
        else:
            counts[table] = 0
    return {"user_id": user_id, "counts": counts}


def _insert_row(
    store: Store,
    *,
    row_id: str,
    user_id: str,
    tier: str,
    status: str,
    start: datetime,
    end: datetime,
    meta: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    store.execute(
        """
        INSERT INTO user_subscription (
            id, user_id, provider,
            provider_customer_id, provider_subscription_id, provider_plan_id,
            tier, status, billing_period_start, billing_period_end,
            cancel_at_period_end, is_current, provider_metadata,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            row_id,
            user_id,
            "razorpay",
            None,
            None,
            None,
            tier,
            status,
            store.sql_dt(start),
            store.sql_dt(end),
            store.sql_bool(False),
            store.sql_bool(True),
            store.dump_meta(meta),
            store.sql_dt(now),
            store.sql_dt(now),
        ),
    )
    stored = store.fetchone(
        "SELECT * FROM user_subscription WHERE id = %s",
        (row_id,),
    )
    if stored is None:
        raise StagingTestSubscriptionError("insert failed")
    return stored


def _update_row(
    store: Store,
    *,
    row_id: str,
    user_id: str,
    tier: str,
    status: str,
    start: datetime,
    end: datetime,
    cancel: bool,
    meta: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    store.execute(
        """
        UPDATE user_subscription
        SET tier = %s,
            status = %s,
            billing_period_start = %s,
            billing_period_end = %s,
            cancel_at_period_end = %s,
            provider_metadata = %s,
            updated_at = %s
        WHERE id = %s AND user_id = %s
        """,
        (
            tier,
            status,
            store.sql_dt(start),
            store.sql_dt(end),
            store.sql_bool(cancel),
            store.dump_meta(meta),
            store.sql_dt(now),
            row_id,
            user_id,
        ),
    )
    stored = store.fetchone(
        "SELECT * FROM user_subscription WHERE id = %s",
        (row_id,),
    )
    if stored is None:
        raise StagingTestSubscriptionError("update failed")
    return stored


def apply_on_connection(
    conn: Any,
    *,
    allowlist: Allowlist,
    user_id: str,
    state: str,
    now: datetime | None = None,
    commit: bool = False,
    postgres: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    if state not in APPLY_STATES:
        raise StagingTestSubscriptionError(f"unknown state {state!r}")
    clock = as_utc(now or utc_now()).replace(microsecond=0)
    run = run_id or str(uuid.uuid4())
    cohort = allowlist.cohort_for(user_id)
    if state in STABLE_STATES and state != cohort:
        raise StagingTestSubscriptionError("state does not match allowlisted cohort")
    store = Store(conn, postgres=postgres)
    preview: dict[str, Any] = {
        "action": "apply",
        "commit": commit,
        "run_id": run,
        "user_id": user_id,
        "cohort": cohort,
        "state": state,
        "label": allowlist.labels.get(cohort) or None,
        "eligible": True,
    }
    try:
        if commit:
            store.begin()
        else:
            store.begin_read_only()
        current = _select_current(store, user_id, lock=commit)
        _require_clean_or_helper(store, user_id)
        if current is not None:
            if not helper_owned(current):
                raise StagingTestSubscriptionError("current row is not helper-owned")
            _assert_no_drift(current)
            meta = load_meta(current["provider_metadata"])
            recorded = str(meta.get("recorded_state") or "")
            if recorded != cohort:
                raise StagingTestSubscriptionError("recorded_state does not match cohort")
            fixture = str(meta.get("fixture") or "")
            if state in STABLE_STATES:
                if fixture != cohort:
                    raise StagingTestSubscriptionError("use restore for a temporary fixture")
                preview["result"] = "unchanged"
                preview["row_id"] = str(current["id"])
                preview["before"] = comparable(current)
                preview["after"] = comparable(current)
                if commit:
                    store.commit()
                else:
                    store.rollback()
                return preview
            if fixture != cohort:
                raise StagingTestSubscriptionError(
                    "temporary fixture already applied; restore first"
                )
            start, end = period_for(state, clock)
            status = status_for(state)
            baseline = dict(meta["baseline"])
            next_helper = {
                "staging_test_subscription": True,
                "recorded_state": cohort,
                "fixture": state,
                "run_id": run,
            }
            last = {
                "id": str(current["id"]),
                "user_id": user_id,
                "provider": "razorpay",
                "provider_customer_id": None,
                "provider_subscription_id": None,
                "provider_plan_id": None,
                "tier": cohort,
                "status": status,
                "billing_period_start": iso(start),
                "billing_period_end": iso(end),
                "cancel_at_period_end": False,
                "is_current": True,
                "created_at": iso(current["created_at"]),
                "helper_meta": next_helper,
            }
            packed = _helper_meta(
                recorded_state=cohort,
                fixture=state,
                run_id=run,
                baseline=baseline,
                last_helper_state=last,
            )
            before = comparable(current)
            if not commit:
                preview["row_id"] = str(current["id"])
                preview["before"] = before
                preview["after"] = last
                store.rollback()
                return preview
            stored = _update_row(
                store,
                row_id=str(current["id"]),
                user_id=user_id,
                tier=cohort,
                status=status,
                start=start,
                end=end,
                cancel=False,
                meta=packed,
                now=clock,
            )
            after = comparable(stored)
            _write_audit(
                store,
                operator_uuid=allowlist.operator_uuid,
                action=AUDIT_APPLY,
                user_id=user_id,
                target_id=str(stored["id"]),
                before=before,
                after=after,
                reason=f"run_id={run} state={state}",
                now=clock,
            )
            store.commit()
            preview["row_id"] = str(stored["id"])
            preview["before"] = before
            preview["after"] = after
            return preview

        if state not in STABLE_STATES:
            raise StagingTestSubscriptionError("no helper row to apply a temporary state to")
        start, end = period_for(cohort, clock)
        row_id = str(uuid.uuid4())
        created = iso(clock)
        helper = {
            "staging_test_subscription": True,
            "recorded_state": cohort,
            "fixture": cohort,
            "run_id": run,
        }
        last = {
            "id": row_id,
            "user_id": user_id,
            "provider": "razorpay",
            "provider_customer_id": None,
            "provider_subscription_id": None,
            "provider_plan_id": None,
            "tier": cohort,
            "status": "active",
            "billing_period_start": iso(start),
            "billing_period_end": iso(end),
            "cancel_at_period_end": False,
            "is_current": True,
            "created_at": created,
            "helper_meta": helper,
        }
        packed = _helper_meta(
            recorded_state=cohort,
            fixture=cohort,
            run_id=run,
            baseline=dict(last),
            last_helper_state=last,
        )
        if not commit:
            proposed = dict(last)
            proposed["id"] = None
            proposed["created_at"] = None
            preview["before"] = None
            preview["after"] = proposed
            store.rollback()
            return preview
        stored = _insert_row(
            store,
            row_id=row_id,
            user_id=user_id,
            tier=cohort,
            status="active",
            start=start,
            end=end,
            meta=packed,
            now=clock,
        )
        after = comparable(stored)
        _write_audit(
            store,
            operator_uuid=allowlist.operator_uuid,
            action=AUDIT_APPLY,
            user_id=user_id,
            target_id=row_id,
            before=None,
            after=after,
            reason=f"run_id={run} state={cohort}",
            now=clock,
        )
        store.commit()
        preview["row_id"] = row_id
        preview["before"] = None
        preview["after"] = after
        return preview
    except Exception:
        store.rollback()
        raise


def restore_on_connection(
    conn: Any,
    *,
    allowlist: Allowlist,
    user_id: str,
    now: datetime | None = None,
    commit: bool = False,
    postgres: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    clock = as_utc(now or utc_now()).replace(microsecond=0)
    run = run_id or str(uuid.uuid4())
    cohort = allowlist.cohort_for(user_id)
    preview = {
        "action": "restore",
        "commit": commit,
        "run_id": run,
        "user_id": user_id,
        "cohort": cohort,
        "eligible": True,
    }
    store = Store(conn, postgres=postgres)
    try:
        if commit:
            store.begin()
        else:
            store.begin_read_only()
        current = _select_current(store, user_id, lock=commit)
        if current is None:
            raise StagingTestSubscriptionError("no current helper row")
        _require_clean_or_helper(store, user_id)
        _assert_no_drift(current)
        meta = load_meta(current["provider_metadata"])
        baseline = meta.get("baseline")
        if not isinstance(baseline, dict):
            raise StagingTestSubscriptionError("missing baseline")
        end = parse_dt(baseline.get("billing_period_end"))
        if end is None or end <= clock:
            raise StagingTestSubscriptionError(
                "baseline billing period has ended; use renew"
            )
        start = parse_dt(baseline.get("billing_period_start"))
        if start is None:
            raise StagingTestSubscriptionError("baseline is incomplete")
        helper = dict(baseline.get("helper_meta") or {})
        fixture = str(helper.get("fixture") or cohort)
        helper_meta = {
            "staging_test_subscription": True,
            "recorded_state": cohort,
            "fixture": fixture,
            "run_id": run,
        }
        last = {
            "id": str(current["id"]),
            "user_id": user_id,
            "provider": "razorpay",
            "provider_customer_id": None,
            "provider_subscription_id": None,
            "provider_plan_id": None,
            "tier": str(baseline["tier"]),
            "status": str(baseline["status"]),
            "billing_period_start": iso(start),
            "billing_period_end": iso(end),
            "cancel_at_period_end": bool(baseline.get("cancel_at_period_end")),
            "is_current": True,
            "created_at": iso(current["created_at"]),
            "helper_meta": helper_meta,
        }
        packed = _helper_meta(
            recorded_state=cohort,
            fixture=fixture,
            run_id=run,
            baseline=dict(baseline),
            last_helper_state=last,
        )
        before = comparable(current)
        if not commit:
            preview["row_id"] = str(current["id"])
            preview["before"] = before
            preview["after"] = last
            store.rollback()
            return preview
        stored = _update_row(
            store,
            row_id=str(current["id"]),
            user_id=user_id,
            tier=str(baseline["tier"]),
            status=str(baseline["status"]),
            start=start,
            end=end,
            cancel=bool(baseline.get("cancel_at_period_end")),
            meta=packed,
            now=clock,
        )
        after = comparable(stored)
        _write_audit(
            store,
            operator_uuid=allowlist.operator_uuid,
            action=AUDIT_RESTORE,
            user_id=user_id,
            target_id=str(stored["id"]),
            before=before,
            after=after,
            reason=f"run_id={run}",
            now=clock,
        )
        store.commit()
        preview["row_id"] = str(stored["id"])
        preview["before"] = before
        preview["after"] = after
        return preview
    except Exception:
        store.rollback()
        raise


def renew_on_connection(
    conn: Any,
    *,
    allowlist: Allowlist,
    user_id: str,
    now: datetime | None = None,
    commit: bool = False,
    postgres: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    clock = as_utc(now or utc_now()).replace(microsecond=0)
    run = run_id or str(uuid.uuid4())
    cohort = allowlist.cohort_for(user_id)
    start, end = period_for(cohort, clock)
    preview = {
        "action": "renew",
        "commit": commit,
        "run_id": run,
        "user_id": user_id,
        "cohort": cohort,
        "intended": {
            "tier": cohort,
            "status": "active",
            "billing_period_start": iso(start),
            "billing_period_end": iso(end),
        },
        "eligible": True,
    }
    store = Store(conn, postgres=postgres)
    try:
        if commit:
            store.begin()
        else:
            store.begin_read_only()
        current = _select_current(store, user_id, lock=commit)
        if current is None:
            raise StagingTestSubscriptionError("no current helper row")
        _require_clean_or_helper(store, user_id)
        _assert_no_drift(current)
        helper = {
            "staging_test_subscription": True,
            "recorded_state": cohort,
            "fixture": cohort,
            "run_id": run,
        }
        last = {
            "id": str(current["id"]),
            "user_id": user_id,
            "provider": "razorpay",
            "provider_customer_id": None,
            "provider_subscription_id": None,
            "provider_plan_id": None,
            "tier": cohort,
            "status": "active",
            "billing_period_start": iso(start),
            "billing_period_end": iso(end),
            "cancel_at_period_end": False,
            "is_current": True,
            "created_at": iso(current["created_at"]),
            "helper_meta": helper,
        }
        packed = _helper_meta(
            recorded_state=cohort,
            fixture=cohort,
            run_id=run,
            baseline=dict(last),
            last_helper_state=last,
        )
        before = comparable(current)
        if not commit:
            preview["row_id"] = str(current["id"])
            preview["before"] = before
            preview["after"] = last
            store.rollback()
            return preview
        stored = _update_row(
            store,
            row_id=str(current["id"]),
            user_id=user_id,
            tier=cohort,
            status="active",
            start=start,
            end=end,
            cancel=False,
            meta=packed,
            now=clock,
        )
        after = comparable(stored)
        _write_audit(
            store,
            operator_uuid=allowlist.operator_uuid,
            action=AUDIT_RENEW,
            user_id=user_id,
            target_id=str(stored["id"]),
            before=before,
            after=after,
            reason=f"run_id={run}",
            now=clock,
        )
        store.commit()
        preview["row_id"] = str(stored["id"])
        preview["before"] = before
        preview["after"] = after
        return preview
    except Exception:
        store.rollback()
        raise


def reset_on_connection(
    conn: Any,
    *,
    allowlist: Allowlist,
    user_id: str,
    now: datetime | None = None,
    commit: bool = False,
    postgres: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    clock = as_utc(now or utc_now()).replace(microsecond=0)
    run = run_id or str(uuid.uuid4())
    cohort = allowlist.cohort_for(user_id)
    preview = {
        "action": "reset",
        "commit": commit,
        "run_id": run,
        "user_id": user_id,
        "cohort": cohort,
        "intended": "delete helper-owned rows",
        "eligible": True,
    }
    store = Store(conn, postgres=postgres)
    try:
        if commit:
            store.begin()
        else:
            store.begin_read_only()
        rows = _history(store, user_id, lock=commit)
        current = _require_clean_or_helper(store, user_id, rows)
        if current is None and not rows:
            preview["result"] = "already_free"
            preview["before"] = None
            preview["after"] = None
            preview["row_ids"] = []
            if commit:
                store.commit()
            else:
                store.rollback()
            return preview
        if current is not None:
            if not helper_owned(current):
                raise StagingTestSubscriptionError("current row is not helper-owned")
            _assert_no_drift(current)
        before = comparable(current) if current is not None else None
        row_ids: list[str] = []
        for row in rows:
            row_id = str(row["id"])
            if _charge_count(store, row_id):
                raise StagingTestSubscriptionError(
                    "subscription_charge rows exist for this helper row"
                )
            row_ids.append(row_id)
        preview["row_ids"] = row_ids
        preview["before"] = before
        preview["after"] = None
        if not commit:
            store.rollback()
            return preview
        for row_id in row_ids:
            deleted = store.execute(
                "DELETE FROM user_subscription WHERE id = %s AND user_id = %s",
                (row_id, user_id),
            )
            if deleted.rowcount != 1:
                raise StagingTestSubscriptionError(
                    "reset did not delete the exact helper row"
                )
        remaining = store.fetchone(
            "SELECT COUNT(*) AS n FROM user_subscription WHERE user_id = %s",
            (user_id,),
        )
        if remaining is None or int(remaining["n"]) != 0:
            raise StagingTestSubscriptionError(
                "reset left subscription rows behind"
            )
        _write_audit(
            store,
            operator_uuid=allowlist.operator_uuid,
            action=AUDIT_RESET,
            user_id=user_id,
            target_id=",".join(row_ids),
            before=before,
            after=None,
            reason=f"run_id={run}",
            now=clock,
        )
        store.commit()
        return preview
    except Exception:
        store.rollback()
        raise


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _load_operational(
    env: Mapping[str, str], *, need_allowlist: bool
) -> tuple[DsnIdentity, Allowlist | None, str]:
    dsn = (env.get("DATABASE_URL") or "").strip()
    identity = require_operational_context(env, dsn)
    allowlist = load_allowlist(env) if need_allowlist else None
    return identity, allowlist, dsn


def _connect_postgres(dsn: str) -> Any:
    """Connect with explicit keywords. Never pass the raw URL to libpq."""
    target = parse_target(dsn)
    if _approved_candidate(target) not in tuple(DIRECT_STAGING):
        raise StagingTestSubscriptionError(
            "database identity is not the approved staging target"
        )
    import psycopg

    saved = {
        key: os.environ.pop(key) for key in LIBPQ_OVERRIDE_ENV if key in os.environ
    }
    try:
        kwargs: dict[str, Any] = {
            "host": target.host,
            "port": target.port,
            "dbname": target.database,
            "user": target.user,
            "password": target.password,
            "options": "-c default_transaction_read_only=off",
        }
        if target.sslmode:
            kwargs["sslmode"] = target.sslmode
        try:
            return psycopg.connect(**kwargs)
        except Exception as exc:
            raise StagingTestSubscriptionError(
                "could not connect to the approved staging database "
                f"({type(exc).__name__})"
            ) from None
    finally:
        os.environ.update(saved)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "inspect",
            "preview",
            "apply",
            "restore",
            "renew",
            "inventory",
            "reset",
        ),
    )
    parser.add_argument("--email")
    parser.add_argument("--uuid")
    parser.add_argument("--state")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    environ = env if env is not None else os.environ
    try:
        identity, allowlist, dsn = _load_operational(
            environ, need_allowlist=args.command != "inspect"
        )
    except StagingTestSubscriptionError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    redacted = asdict(identity)
    if args.command == "preview":
        args.command = "apply"
        args.commit = False

    commit = bool(args.commit)
    targets: list[str] = []
    if args.command != "inspect":
        if allowlist is None:
            print("allowlist is required", file=sys.stderr)
            return 2
        if args.all:
            targets = [allowlist.uuids[cohort] for cohort in COHORTS]
        elif args.uuid:
            try:
                targets = [str(uuid.UUID(args.uuid))]
            except ValueError:
                print("not a UUID", file=sys.stderr)
                return 1
            allowlist.cohort_for(targets[0])

    conn = None
    try:
        conn = _connect_postgres(dsn)
        if args.command == "inspect":
            if not args.email:
                print("--email is required for inspect", file=sys.stderr)
                return 1
            _print_json(
                {
                    "database": redacted,
                    "account": inspect_on_connection(
                        conn, email=args.email, postgres=True
                    ),
                }
            )
            return 0
        if allowlist is None:
            print("allowlist is required", file=sys.stderr)
            return 2
        if not targets:
            print("--uuid or --all is required", file=sys.stderr)
            return 1
        results = []
        for user_id in targets:
            try:
                if args.command == "inventory":
                    results.append(
                        inventory_on_connection(conn, user_id, postgres=True)
                    )
                    continue
                if args.command == "apply":
                    state = args.state
                    if args.all:
                        state = allowlist.cohort_for(user_id)
                    if not state:
                        print("--state is required unless --all", file=sys.stderr)
                        return 1
                    results.append(
                        apply_on_connection(
                            conn,
                            allowlist=allowlist,
                            user_id=user_id,
                            state=state,
                            commit=commit,
                            postgres=True,
                        )
                    )
                    continue
                if args.command == "restore":
                    results.append(
                        restore_on_connection(
                            conn,
                            allowlist=allowlist,
                            user_id=user_id,
                            commit=commit,
                            postgres=True,
                        )
                    )
                    continue
                if args.command == "renew":
                    results.append(
                        renew_on_connection(
                            conn,
                            allowlist=allowlist,
                            user_id=user_id,
                            commit=commit,
                            postgres=True,
                        )
                    )
                    continue
                if args.command == "reset":
                    results.append(
                        reset_on_connection(
                            conn,
                            allowlist=allowlist,
                            user_id=user_id,
                            commit=commit,
                            postgres=True,
                        )
                    )
            except StagingTestSubscriptionError as exc:
                if commit:
                    raise
                results.append(
                    {
                        "user_id": user_id,
                        "commit": False,
                        "eligible": False,
                        "error": str(exc),
                    }
                )
        _print_json({"database": redacted, "results": results, "commit": commit})
        if any(isinstance(item, dict) and item.get("error") for item in results):
            return 2
        return 0
    except StagingTestSubscriptionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
