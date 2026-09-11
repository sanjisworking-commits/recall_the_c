"""User-owned Playground subscriptions. Isolation is application-level (user_id)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from constitution_memorizer.progress.user_ids import as_user_id
from constitution_memorizer.subscriptions.errors import (
    CurrentSubscriptionExistsError,
    DuplicateProviderSubscriptionError,
    InvalidSubscriptionValue,
)
from constitution_memorizer.subscriptions.models import (
    PROVIDER_RAZORPAY,
    UserSubscription,
    require_provider,
    require_status,
    require_tier,
)

_UNSET = object()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _metadata_dumps(value: Mapping[str, Any] | None) -> str:
    payload = dict(value or {})
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _metadata_loads(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return dict(value)
    return json.loads(value)


def _raise_integrity(exc: BaseException) -> None:
    constraint = str(getattr(getattr(exc, "diag", None), "constraint_name", "") or "")
    msg = f"{constraint} {exc}".lower()
    if "user_subscription_one_current" in msg or (
        "unique" in msg
        and "user_id" in msg
        and "provider_subscription" not in msg
        and "provider_sub" not in msg
    ):
        raise CurrentSubscriptionExistsError(
            "a current commercial subscription already exists for this user"
        ) from exc
    if (
        "user_subscription_provider_sub_id" in msg
        or "provider_sub" in msg
        or "provider_subscription" in msg
        or ("unique" in msg and "provider" in msg)
    ):
        raise DuplicateProviderSubscriptionError(
            "provider subscription id is already stored"
        ) from exc
    if "check" in msg:
        raise InvalidSubscriptionValue(
            "subscription row failed a database check"
        ) from exc
    raise CurrentSubscriptionExistsError(
        "subscription uniqueness constraint rejected the write"
    ) from exc


def subscription_from_mapping(row: Mapping[str, Any]) -> UserSubscription:
    return UserSubscription(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        provider=str(row["provider"]),
        provider_customer_id=row["provider_customer_id"],
        provider_subscription_id=row["provider_subscription_id"],
        provider_plan_id=row["provider_plan_id"],
        tier=str(row["tier"]),
        status=str(row["status"]),
        billing_period_start=_parse_dt(row["billing_period_start"]),
        billing_period_end=_parse_dt(row["billing_period_end"]),
        cancel_at_period_end=bool(row["cancel_at_period_end"]),
        is_current=bool(row["is_current"]),
        provider_metadata=_metadata_loads(row["provider_metadata"]),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


class SqliteSubscriptionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_current_subscription(self, user_id: UUID | str) -> UserSubscription | None:
        row = self.conn.execute(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE user_id = ? AND is_current = 1
            """,
            (as_user_id(user_id),),
        ).fetchone()
        if row is None:
            return None
        return subscription_from_mapping(row)

    def get_subscription(
        self, user_id: UUID | str, subscription_id: str
    ) -> UserSubscription | None:
        row = self.conn.execute(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE user_id = ? AND id = ?
            """,
            (as_user_id(user_id), subscription_id),
        ).fetchone()
        if row is None:
            return None
        return subscription_from_mapping(row)

    def get_subscription_by_provider_id(
        self, provider_subscription_id: str, *, provider: str = PROVIDER_RAZORPAY
    ) -> UserSubscription | None:
        row = self.conn.execute(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE provider = ? AND provider_subscription_id = ?
            """,
            (require_provider(provider), provider_subscription_id),
        ).fetchone()
        if row is None:
            return None
        return subscription_from_mapping(row)

    def list_subscription_history(self, user_id: UUID | str) -> list[UserSubscription]:
        rows = self.conn.execute(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE user_id = ?
            ORDER BY created_at ASC
            """,
            (as_user_id(user_id),),
        ).fetchall()
        return [subscription_from_mapping(row) for row in rows]

    def create_subscription_record(
        self,
        user_id: UUID | str,
        *,
        tier: str,
        status: str,
        provider: str = PROVIDER_RAZORPAY,
        provider_customer_id: str | None = None,
        provider_subscription_id: str | None = None,
        provider_plan_id: str | None = None,
        billing_period_start: datetime | None = None,
        billing_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
        is_current: bool = True,
        provider_metadata: Mapping[str, Any] | None = None,
    ) -> UserSubscription:
        uid = as_user_id(user_id)
        now = _utc_now()
        row_id = str(uuid4())
        try:
            self.conn.execute(
                """
                INSERT INTO user_subscription (
                    id, user_id, provider, provider_customer_id,
                    provider_subscription_id, provider_plan_id, tier, status,
                    billing_period_start, billing_period_end, cancel_at_period_end,
                    is_current, provider_metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    uid,
                    require_provider(provider),
                    provider_customer_id,
                    provider_subscription_id,
                    provider_plan_id,
                    require_tier(tier),
                    require_status(status),
                    _dt_iso(billing_period_start),
                    _dt_iso(billing_period_end),
                    1 if cancel_at_period_end else 0,
                    1 if is_current else 0,
                    _metadata_dumps(provider_metadata),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            _raise_integrity(exc)
        stored = self.get_subscription(uid, row_id)
        assert stored is not None
        return stored

    def update_subscription_state(
        self,
        user_id: UUID | str,
        subscription_id: str,
        *,
        status: Any = _UNSET,
        billing_period_start: Any = _UNSET,
        billing_period_end: Any = _UNSET,
        cancel_at_period_end: Any = _UNSET,
        provider_customer_id: Any = _UNSET,
        provider_subscription_id: Any = _UNSET,
        provider_plan_id: Any = _UNSET,
        provider_metadata: Any = _UNSET,
    ) -> UserSubscription:
        existing = self.get_subscription(user_id, subscription_id)
        if existing is None:
            raise InvalidSubscriptionValue("subscription not found for user")
        next_status = (
            existing.status if status is _UNSET else require_status(status)
        )
        next_start = (
            existing.billing_period_start
            if billing_period_start is _UNSET
            else billing_period_start
        )
        next_end = (
            existing.billing_period_end
            if billing_period_end is _UNSET
            else billing_period_end
        )
        next_cancel = (
            existing.cancel_at_period_end
            if cancel_at_period_end is _UNSET
            else bool(cancel_at_period_end)
        )
        next_customer = (
            existing.provider_customer_id
            if provider_customer_id is _UNSET
            else provider_customer_id
        )
        next_sub = (
            existing.provider_subscription_id
            if provider_subscription_id is _UNSET
            else provider_subscription_id
        )
        next_plan = (
            existing.provider_plan_id
            if provider_plan_id is _UNSET
            else provider_plan_id
        )
        next_meta = (
            existing.provider_metadata
            if provider_metadata is _UNSET
            else provider_metadata
        )
        now = _utc_now()
        try:
            self.conn.execute(
                """
                UPDATE user_subscription
                SET status = ?,
                    billing_period_start = ?,
                    billing_period_end = ?,
                    cancel_at_period_end = ?,
                    provider_customer_id = ?,
                    provider_subscription_id = ?,
                    provider_plan_id = ?,
                    provider_metadata = ?,
                    updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (
                    next_status,
                    _dt_iso(next_start),
                    _dt_iso(next_end),
                    1 if next_cancel else 0,
                    next_customer,
                    next_sub,
                    next_plan,
                    _metadata_dumps(next_meta),
                    now.isoformat(),
                    as_user_id(user_id),
                    subscription_id,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            _raise_integrity(exc)
        stored = self.get_subscription(user_id, subscription_id)
        assert stored is not None
        return stored

    def mark_not_current(self, user_id: UUID | str, subscription_id: str) -> UserSubscription:
        existing = self.get_subscription(user_id, subscription_id)
        if existing is None:
            raise InvalidSubscriptionValue("subscription not found for user")
        now = _utc_now()
        self.conn.execute(
            """
            UPDATE user_subscription
            SET is_current = 0, updated_at = ?
            WHERE user_id = ? AND id = ?
            """,
            (now.isoformat(), as_user_id(user_id), subscription_id),
        )
        self.conn.commit()
        stored = self.get_subscription(user_id, subscription_id)
        assert stored is not None
        return stored
