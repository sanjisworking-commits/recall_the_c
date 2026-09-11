"""Postgres Playground subscriptions. Isolation is application-level (ENABLE RLS, no policies)."""

from __future__ import annotations

from datetime import datetime
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
from constitution_memorizer.subscriptions.repository import (
    _UNSET,
    _metadata_dumps,
    _raise_integrity,
    _utc_now,
    subscription_from_mapping,
)

try:
    from psycopg.errors import CheckViolation, UniqueViolation
    from psycopg.types.json import Json
except ImportError:  # pragma: no cover
    class UniqueViolation(Exception):
        pass

    class CheckViolation(Exception):
        pass

    Json = None  # type: ignore[misc, assignment]


class PostgresSubscriptionRepository:
    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def _one(
        self, sql: str, params: tuple[Any, ...]
    ) -> UserSubscription | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        if row is None:
            return None
        return subscription_from_mapping(row)

    def get_current_subscription(self, user_id: UUID | str) -> UserSubscription | None:
        return self._one(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE user_id = %s AND is_current = TRUE
            """,
            (as_user_id(user_id),),
        )

    def get_subscription(
        self, user_id: UUID | str, subscription_id: str
    ) -> UserSubscription | None:
        return self._one(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE user_id = %s AND id = %s
            """,
            (as_user_id(user_id), subscription_id),
        )

    def get_subscription_by_provider_id(
        self, provider_subscription_id: str, *, provider: str = PROVIDER_RAZORPAY
    ) -> UserSubscription | None:
        return self._one(
            """
            SELECT id, user_id, provider, provider_customer_id,
                   provider_subscription_id, provider_plan_id, tier, status,
                   billing_period_start, billing_period_end, cancel_at_period_end,
                   is_current, provider_metadata, created_at, updated_at
            FROM user_subscription
            WHERE provider = %s AND provider_subscription_id = %s
            """,
            (require_provider(provider), provider_subscription_id),
        )

    def list_subscription_history(self, user_id: UUID | str) -> list[UserSubscription]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, user_id, provider, provider_customer_id,
                           provider_subscription_id, provider_plan_id, tier, status,
                           billing_period_start, billing_period_end,
                           cancel_at_period_end, is_current, provider_metadata,
                           created_at, updated_at
                    FROM user_subscription
                    WHERE user_id = %s
                    ORDER BY created_at ASC
                    """,
                    (as_user_id(user_id),),
                )
                rows = cur.fetchall()
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
        meta = dict(provider_metadata or {})
        payload = Json(meta) if Json is not None else _metadata_dumps(meta)
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO user_subscription (
                            id, user_id, provider, provider_customer_id,
                            provider_subscription_id, provider_plan_id, tier, status,
                            billing_period_start, billing_period_end,
                            cancel_at_period_end, is_current, provider_metadata,
                            created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        RETURNING id, user_id, provider, provider_customer_id,
                                  provider_subscription_id, provider_plan_id, tier,
                                  status, billing_period_start, billing_period_end,
                                  cancel_at_period_end, is_current, provider_metadata,
                                  created_at, updated_at
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
                            billing_period_start,
                            billing_period_end,
                            cancel_at_period_end,
                            is_current,
                            payload,
                            now,
                            now,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except UniqueViolation as exc:
            _raise_integrity(exc)
        except CheckViolation as exc:
            raise InvalidSubscriptionValue(
                "subscription row failed a database check"
            ) from exc
        assert row is not None
        return subscription_from_mapping(row)

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
        next_status = existing.status if status is _UNSET else require_status(status)
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
            existing.provider_plan_id if provider_plan_id is _UNSET else provider_plan_id
        )
        next_meta = (
            existing.provider_metadata
            if provider_metadata is _UNSET
            else provider_metadata
        )
        now = _utc_now()
        meta = dict(next_meta or {})
        payload = Json(meta) if Json is not None else _metadata_dumps(meta)
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        UPDATE user_subscription
                        SET status = %s,
                            billing_period_start = %s,
                            billing_period_end = %s,
                            cancel_at_period_end = %s,
                            provider_customer_id = %s,
                            provider_subscription_id = %s,
                            provider_plan_id = %s,
                            provider_metadata = %s,
                            updated_at = %s
                        WHERE user_id = %s AND id = %s
                        RETURNING id, user_id, provider, provider_customer_id,
                                  provider_subscription_id, provider_plan_id, tier,
                                  status, billing_period_start, billing_period_end,
                                  cancel_at_period_end, is_current, provider_metadata,
                                  created_at, updated_at
                        """,
                        (
                            next_status,
                            next_start,
                            next_end,
                            next_cancel,
                            next_customer,
                            next_sub,
                            next_plan,
                            payload,
                            now,
                            as_user_id(user_id),
                            subscription_id,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except UniqueViolation as exc:
            _raise_integrity(exc)
        except CheckViolation as exc:
            raise InvalidSubscriptionValue(
                "subscription row failed a database check"
            ) from exc
        if row is None:
            raise InvalidSubscriptionValue("subscription not found for user")
        return subscription_from_mapping(row)

    def mark_not_current(
        self, user_id: UUID | str, subscription_id: str
    ) -> UserSubscription:
        existing = self.get_subscription(user_id, subscription_id)
        if existing is None:
            raise InvalidSubscriptionValue("subscription not found for user")
        now = _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    UPDATE user_subscription
                    SET is_current = FALSE, updated_at = %s
                    WHERE user_id = %s AND id = %s
                    RETURNING id, user_id, provider, provider_customer_id,
                              provider_subscription_id, provider_plan_id, tier,
                              status, billing_period_start, billing_period_end,
                              cancel_at_period_end, is_current, provider_metadata,
                              created_at, updated_at
                    """,
                    (now, as_user_id(user_id), subscription_id),
                )
                row = cur.fetchone()
                conn.commit()
        assert row is not None
        return subscription_from_mapping(row)
