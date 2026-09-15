"""SQLite webhook event reservations. Not a user-owned entitlement table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Mapping
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
from constitution_memorizer.subscriptions.repository import _dt_iso, _parse_dt, _utc_now

_SELECT = """
    SELECT id, provider, provider_event_id, event_name, provider_subscription_id,
           event_created_at, received_at, payload_sha256, processing_status,
           attempt_count, processed_at, last_error_code, created_at, updated_at
    FROM subscription_webhook_event
"""


def webhook_event_from_mapping(row: Mapping[str, Any]) -> WebhookEvent:
    return WebhookEvent(
        id=str(row["id"]),
        provider=str(row["provider"]),
        provider_event_id=str(row["provider_event_id"]),
        event_name=str(row["event_name"]),
        provider_subscription_id=row["provider_subscription_id"],
        event_created_at=_parse_dt(row["event_created_at"]),
        received_at=_parse_dt(row["received_at"]) or _utc_now(),
        payload_sha256=str(row["payload_sha256"]),
        processing_status=str(row["processing_status"]),
        attempt_count=int(row["attempt_count"] or 1),
        processed_at=_parse_dt(row["processed_at"]),
        last_error_code=row["last_error_code"],
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


class SqliteWebhookEventRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_event_by_provider_event_id(
        self,
        provider_event_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> WebhookEvent | None:
        row = self.conn.execute(
            _SELECT + " WHERE provider = ? AND provider_event_id = ?",
            (require_provider(provider), provider_event_id),
        ).fetchone()
        if row is None:
            return None
        return webhook_event_from_mapping(row)

    def list_recent_problem_events(self, *, limit: int = 50) -> list[WebhookEvent]:
        capped = max(1, min(int(limit), 200))
        rows = self.conn.execute(
            _SELECT
            + """
            WHERE processing_status IN ('failed', 'unmatched')
            ORDER BY received_at DESC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()
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
        """Insert processing, or inspect/claim an existing event-id row.

        Returns (event, owned). owned=True means this delivery must process.
        """
        now = _utc_now()
        row_id = str(uuid4())
        try:
            self.conn.execute(
                """
                INSERT INTO subscription_webhook_event (
                    id, provider, provider_event_id, event_name,
                    provider_subscription_id, event_created_at, received_at,
                    payload_sha256, processing_status, attempt_count,
                    processed_at, last_error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing', 1, NULL, NULL, ?, ?)
                """,
                (
                    row_id,
                    require_provider(provider),
                    provider_event_id,
                    event_name,
                    provider_subscription_id,
                    _dt_iso(event_created_at),
                    now.isoformat(),
                    payload_sha256,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            existing = self.get_event_by_provider_event_id(
                provider_event_id, provider=provider
            )
            if existing is None:
                raise DuplicateWebhookEventError(
                    "provider event id is already stored"
                ) from exc
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
        stored = self.get_event_by_provider_event_id(
            provider_event_id, provider=provider
        )
        assert stored is not None
        return stored, True

    def claim_failed_for_retry(
        self,
        provider_event_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> WebhookEvent | None:
        now = _utc_now()
        cursor = self.conn.execute(
            """
            UPDATE subscription_webhook_event
            SET processing_status = 'processing',
                attempt_count = attempt_count + 1,
                last_error_code = NULL,
                processed_at = NULL,
                updated_at = ?
            WHERE provider = ? AND provider_event_id = ?
              AND processing_status = 'failed'
            """,
            (now.isoformat(), require_provider(provider), provider_event_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            return None
        return self.get_event_by_provider_event_id(
            provider_event_id, provider=provider
        )

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
        processed_at = now.isoformat() if terminal else None
        existing = self.conn.execute(
            _SELECT + " WHERE id = ?",
            (event_id,),
        ).fetchone()
        if existing is None:
            raise InvalidSubscriptionValue("webhook event not found")
        sub_id = (
            existing["provider_subscription_id"]
            if provider_subscription_id is None
            else provider_subscription_id
        )
        self.conn.execute(
            """
            UPDATE subscription_webhook_event
            SET processing_status = ?,
                last_error_code = ?,
                processed_at = ?,
                provider_subscription_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                next_status,
                error_code,
                processed_at,
                sub_id,
                now.isoformat(),
                event_id,
            ),
        )
        self.conn.commit()
        row = self.conn.execute(_SELECT + " WHERE id = ?", (event_id,)).fetchone()
        assert row is not None
        return webhook_event_from_mapping(row)
