"""Razorpay subscription webhook processor. Notification in; provider GET is truth.

Does not authorize Playground access. Refunds and disputes reuse this endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from constitution_memorizer.subscriptions.charge_sync import ChargeRecorder
from constitution_memorizer.subscriptions.errors import (
    SubscriptionConfigError,
    SubscriptionProviderError,
    WebhookSignatureError,
)
from constitution_memorizer.subscriptions.models import ACK_WEBHOOK_STATUSES
from constitution_memorizer.subscriptions.webhook_signature import (
    WebhookSecrets,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

SUPPORTED_SUBSCRIPTION_EVENTS = frozenset(
    {
        "subscription.authenticated",
        "subscription.activated",
        "subscription.charged",
        "subscription.completed",
        "subscription.updated",
        "subscription.pending",
        "subscription.halted",
        "subscription.paused",
        "subscription.resumed",
        "subscription.cancelled",
    }
)
SUPPORTED_REFUND_EVENTS = frozenset(
    {
        "refund.created",
        "refund.processed",
        "refund.failed",
    }
)
SUPPORTED_DISPUTE_EVENTS = frozenset(
    {
        "payment.dispute.created",
        "payment.dispute.won",
        "payment.dispute.lost",
    }
)
SUPPORTED_PAYMENT_EVENTS = SUPPORTED_REFUND_EVENTS | SUPPORTED_DISPUTE_EVENTS


@dataclass(frozen=True)
class WebhookDeliveryResult:
    status_code: int
    error: str | None = None
    processing_status: str | None = None
    used_secret_slot: str | None = None
    owned: bool = False


class WebhookProcessor:
    def __init__(
        self,
        *,
        events: Any,
        subscriptions: Any,
        service: Any,
        secrets: WebhookSecrets,
        charges: Any = None,
    ) -> None:
        self._events = events
        self._subscriptions = subscriptions
        self._service = service
        self._secrets = secrets
        self._charges = charges
        self._recorder = (
            ChargeRecorder(charges, subscriptions, service)
            if charges is not None
            else None
        )

    def process_delivery(
        self,
        raw_body: bytes,
        signature: str,
        event_id: str,
    ) -> WebhookDeliveryResult:
        try:
            used_slot = verify_webhook_signature(raw_body, signature, self._secrets)
        except SubscriptionConfigError:
            logger.warning("subscription webhook rejected: webhook secret is not configured")
            return WebhookDeliveryResult(503, error="config")
        except WebhookSignatureError:
            logger.warning("subscription webhook rejected: invalid signature")
            return WebhookDeliveryResult(400, error="invalid_signature")

        provider_event_id = str(event_id or "").strip()
        if not provider_event_id:
            logger.warning(
                "subscription webhook rejected: missing event id used_secret_slot=%s",
                used_slot,
            )
            return WebhookDeliveryResult(
                400, error="missing_event_id", used_secret_slot=used_slot
            )

        payload = _parse_json_object(raw_body)
        if payload is None:
            logger.warning(
                "subscription webhook rejected: invalid json provider_event_id=%s used_secret_slot=%s",
                provider_event_id,
                used_slot,
            )
            return WebhookDeliveryResult(
                400, error="invalid_json", used_secret_slot=used_slot
            )

        event_name = str(payload.get("event") or "").strip() or "unknown"
        provider_sub_id = _provider_subscription_id(payload)
        digest = hashlib.sha256(raw_body).hexdigest()
        event, owned = self._events.reserve_event(
            provider_event_id=provider_event_id,
            event_name=event_name,
            payload_sha256=digest,
            provider_subscription_id=provider_sub_id,
            event_created_at=_event_created_at(payload),
        )
        if not owned:
            if event.processing_status not in ACK_WEBHOOK_STATUSES:
                logger.info(
                    "subscription webhook provider_event_id=%s event_name=%s "
                    "provider_subscription_id=%s result=retry_busy attempt=%s "
                    "used_secret_slot=%s",
                    provider_event_id,
                    event_name,
                    event.provider_subscription_id,
                    event.attempt_count,
                    used_slot,
                )
                return WebhookDeliveryResult(
                    503,
                    error="provider",
                    processing_status=event.processing_status,
                    used_secret_slot=used_slot,
                    owned=False,
                )
            logger.info(
                "subscription webhook provider_event_id=%s event_name=%s "
                "provider_subscription_id=%s result=duplicate status=%s attempt=%s "
                "used_secret_slot=%s",
                provider_event_id,
                event_name,
                event.provider_subscription_id,
                event.processing_status,
                event.attempt_count,
                used_slot,
            )
            return WebhookDeliveryResult(
                200,
                processing_status=event.processing_status,
                used_secret_slot=used_slot,
                owned=False,
            )

        try:
            result = self._process_owned(
                event,
                event_name=event_name,
                provider_sub_id=provider_sub_id,
                payload=payload,
                used_slot=used_slot,
            )
        except Exception:
            logger.exception(
                "subscription webhook provider_event_id=%s event_name=%s "
                "provider_subscription_id=%s result=failed attempt=%s "
                "used_secret_slot=%s",
                provider_event_id,
                event_name,
                provider_sub_id,
                event.attempt_count,
                used_slot,
            )
            self._events.mark_event_status(event.id, "failed", error_code="internal")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )
        return result

    def _process_owned(
        self,
        event: Any,
        *,
        event_name: str,
        provider_sub_id: str | None,
        payload: Mapping[str, Any],
        used_slot: str,
    ) -> WebhookDeliveryResult:
        if event_name in SUPPORTED_PAYMENT_EVENTS:
            return self._process_payment_event(
                event,
                event_name=event_name,
                payload=payload,
                used_slot=used_slot,
            )
        if event_name not in SUPPORTED_SUBSCRIPTION_EVENTS:
            stored = self._events.mark_event_status(event.id, "ignored")
            self._log(stored, used_slot, "ignored")
            return WebhookDeliveryResult(
                200,
                processing_status="ignored",
                used_secret_slot=used_slot,
                owned=True,
            )
        if not provider_sub_id:
            stored = self._events.mark_event_status(
                event.id, "ignored", error_code="missing_subscription_id"
            )
            self._log(stored, used_slot, "ignored")
            return WebhookDeliveryResult(
                200,
                processing_status="ignored",
                used_secret_slot=used_slot,
                owned=True,
            )

        local = self._subscriptions.get_subscription_by_provider_id(provider_sub_id)
        if local is None:
            stored = self._events.mark_event_status(
                event.id,
                "unmatched",
                provider_subscription_id=provider_sub_id,
            )
            self._log(stored, used_slot, "unmatched")
            return WebhookDeliveryResult(
                200,
                processing_status="unmatched",
                used_secret_slot=used_slot,
                owned=True,
            )

        try:
            provider = self._service.fetch_provider_subscription(provider_sub_id)
        except SubscriptionProviderError:
            stored = self._events.mark_event_status(
                event.id,
                "failed",
                error_code="provider",
                provider_subscription_id=provider_sub_id,
            )
            self._log(stored, used_slot, "failed")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )

        extra: dict[str, Any] = {}
        if event_name == "subscription.charged":
            extra["last_charge_event_id"] = event.provider_event_id
            extra["last_charge_processed_at"] = datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat()
        try:
            stored_row = self._service.reconcile_fetched_subscription(
                local, provider, extra_meta=extra or None
            )
            if event_name == "subscription.charged" and self._recorder is not None:
                self._recorder.record_charged_payload(payload, stored_row)
        except SubscriptionProviderError:
            stored = self._events.mark_event_status(
                event.id,
                "failed",
                error_code="provider",
                provider_subscription_id=provider_sub_id,
            )
            self._log(stored, used_slot, "failed")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )
        except Exception:
            logger.exception(
                "subscription webhook provider_event_id=%s event_name=%s "
                "provider_subscription_id=%s result=failed attempt=%s "
                "used_secret_slot=%s",
                event.provider_event_id,
                event_name,
                provider_sub_id,
                event.attempt_count,
                used_slot,
            )
            stored = self._events.mark_event_status(
                event.id,
                "failed",
                error_code="persist",
                provider_subscription_id=provider_sub_id,
            )
            self._log(stored, used_slot, "failed")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )

        stored = self._events.mark_event_status(
            event.id,
            "processed",
            provider_subscription_id=provider_sub_id,
        )
        self._log(stored, used_slot, "processed")
        return WebhookDeliveryResult(
            200,
            processing_status="processed",
            used_secret_slot=used_slot,
            owned=True,
        )

    def _process_payment_event(
        self,
        event: Any,
        *,
        event_name: str,
        payload: Mapping[str, Any],
        used_slot: str,
    ) -> WebhookDeliveryResult:
        if self._recorder is None:
            stored = self._events.mark_event_status(
                event.id, "failed", error_code="provider"
            )
            self._log(stored, used_slot, "failed")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )
        try:
            if event_name in SUPPORTED_REFUND_EVENTS:
                status, sub_id = self._recorder.apply_refund(payload)
            else:
                status, sub_id = self._recorder.apply_dispute(payload)
        except SubscriptionProviderError:
            stored = self._events.mark_event_status(
                event.id, "failed", error_code="provider"
            )
            self._log(stored, used_slot, "failed")
            return WebhookDeliveryResult(
                503,
                error="provider",
                processing_status="failed",
                used_secret_slot=used_slot,
                owned=True,
            )
        stored = self._events.mark_event_status(
            event.id,
            status,
            provider_subscription_id=sub_id,
        )
        self._log(stored, used_slot, status)
        return WebhookDeliveryResult(
            200,
            processing_status=status,
            used_secret_slot=used_slot,
            owned=True,
        )

    def _log(self, event: Any, used_slot: str, result: str) -> None:
        logger.info(
            "subscription webhook provider_event_id=%s event_name=%s "
            "provider_subscription_id=%s result=%s attempt=%s used_secret_slot=%s",
            event.provider_event_id,
            event.event_name,
            event.provider_subscription_id,
            result,
            event.attempt_count,
            used_slot,
        )


def _parse_json_object(raw_body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _provider_subscription_id(payload: Mapping[str, Any]) -> str | None:
    body = payload.get("payload")
    if not isinstance(body, dict):
        return None
    subscription = body.get("subscription")
    if not isinstance(subscription, dict):
        return None
    entity = subscription.get("entity")
    if not isinstance(entity, dict):
        return None
    sub_id = str(entity.get("id") or "").strip()
    return sub_id or None


def _event_created_at(payload: Mapping[str, Any]) -> datetime | None:
    value = payload.get("created_at")
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
