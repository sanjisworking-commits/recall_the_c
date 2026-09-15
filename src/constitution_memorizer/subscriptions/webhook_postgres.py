"""Postgres webhook event reservations. Isolation is application-level."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from constitution_memorizer.subscriptions.errors import (
    DuplicateWebhookEventError,
    InvalidSubscriptionValue,
)
from constitution_memorizer.subscriptions.models import (
    PROVIDER_RAZORPAY,
    WebhookEvent,
    require_provider,
    require_webhook_status,
)
from constitution_memorizer.subscriptions.repository import _utc_now
from constitution_memorizer.subscriptions.webhook_repository import (
    webhook_event_from_mapping,
)

try:
    from psycopg.errors import CheckViolation, UniqueViolation
except ImportError:  # pragma: no cover
    class UniqueViolation(Exception):
        pass

    class CheckViolation(Exception):
        pass

_SELECT = """
    SELECT id, provider, provider_event_id, event_name, provider_subscription_id,
           event_created_at, received_at, payload_sha256, processing_status,
           attempt_count, processed_at, last_error_code, created_at, updated_at
    FROM subscription_webhook_event
"""


class PostgresWebhookEventRepository:
    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def _one(self, sql: str, params: tuple[Any, ...]) -> WebhookEvent | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        if row is None:
            return None
        return webhook_event_from_mapping(row)

    def get_event_by_provider_event_id(
        self,
        provider_event_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> WebhookEvent | None:
        return self._one(
            _SELECT + " WHERE provider = %s AND provider_event_id = %s",
            (require_provider(provider), provider_event_id),
        )

    def list_recent_problem_events(self, *, limit: int = 50) -> list[WebhookEvent]:
        capped = max(1, min(int(limit), 200))
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _SELECT
                    + """
                    WHERE processing_status IN ('failed', 'unmatched')
                    ORDER BY received_at DESC
                    LIMIT %s
                    """,
                    (capped,),
                )
                rows = cur.fetchall()
        return [webhook_event_from_mapping(row) for row in rows]

    def reserve_event(
        self,
        *,
        provider_event_id: str,
        event_name: str,
        payload_sha256: str,
        provider_subscription_id: str | None = None,
        event_created_at: datetime | None = None,
        provider: str = PROVIDER_RAZORPAY,
    ) -> tuple[WebhookEvent, bool]:
        now = _utc_now()
        row_id = str(uuid4())
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO subscription_webhook_event (
                            id, provider, provider_event_id, event_name,
                            provider_subscription_id, event_created_at, received_at,
                            payload_sha256, processing_status, attempt_count,
                            processed_at, last_error_code, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, 'processing', 1,
                            NULL, NULL, %s, %s
                        )
                        RETURNING id, provider, provider_event_id, event_name,
                                  provider_subscription_id, event_created_at,
                                  received_at, payload_sha256, processing_status,
                                  attempt_count, processed_at, last_error_code,
                                  created_at, updated_at
                        """,
                        (
                            row_id,
                            require_provider(provider),
                            provider_event_id,
                            event_name,
                            provider_subscription_id,
                            event_created_at,
                            now,
                            payload_sha256,
                            now,
                            now,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except UniqueViolation:
            existing = self.get_event_by_provider_event_id(
                provider_event_id, provider=provider
            )
            if existing is None:
                raise DuplicateWebhookEventError(
                    "provider event id is already stored"
                )
            if existing.processing_status == "failed":
                claimed = self.claim_failed_for_retry(
                    provider_event_id, provider=provider
                )
                if claimed is not None:
                    return claimed, True
                existing = self.get_event_by_provider_event_id(
                    provider_event_id, provider=provider
                ) or existing
            return existing, False
        except CheckViolation as exc:
            raise InvalidSubscriptionValue(
                "webhook event row failed a database check"
            ) from exc
        assert row is not None
        return webhook_event_from_mapping(row), True

    def claim_failed_for_retry(
        self,
        provider_event_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> WebhookEvent | None:
        now = _utc_now()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    """
                    UPDATE subscription_webhook_event
                    SET processing_status = 'processing',
                        attempt_count = attempt_count + 1,
                        last_error_code = NULL,
                        processed_at = NULL,
                        updated_at = %s
                    WHERE provider = %s AND provider_event_id = %s
                      AND processing_status = 'failed'
                    RETURNING id, provider, provider_event_id, event_name,
                              provider_subscription_id, event_created_at,
                              received_at, payload_sha256, processing_status,
                              attempt_count, processed_at, last_error_code,
                              created_at, updated_at
                    """,
                    (now, require_provider(provider), provider_event_id),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            return None
        return webhook_event_from_mapping(row)

    def mark_event_status(
        self,
        event_id: str,
        status: str,
        *,
        error_code: str | None = None,
        provider_subscription_id: str | None = None,
    ) -> WebhookEvent:
        next_status = require_webhook_status(status)
        now = _utc_now()
        terminal = next_status in {"processed", "ignored", "unmatched"}
        processed_at = now if terminal else None
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        UPDATE subscription_webhook_event
                        SET processing_status = %s,
                            last_error_code = %s,
                            processed_at = %s,
                            provider_subscription_id = COALESCE(%s, provider_subscription_id),
                            updated_at = %s
                        WHERE id = %s
                        RETURNING id, provider, provider_event_id, event_name,
                                  provider_subscription_id, event_created_at,
                                  received_at, payload_sha256, processing_status,
                                  attempt_count, processed_at, last_error_code,
                                  created_at, updated_at
                        """,
                        (
                            next_status,
                            error_code,
                            processed_at,
                            provider_subscription_id,
                            now,
                            event_id,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except CheckViolation as exc:
            raise InvalidSubscriptionValue(
                "webhook event row failed a database check"
            ) from exc
        if row is None:
            raise InvalidSubscriptionValue("webhook event not found")
        return webhook_event_from_mapping(row)
