"""Payment → invoice → subscription_charge linkage. Not entitlement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from constitution_memorizer.subscriptions.razorpay import ProviderPayment


def payload_entity(payload: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    body = payload.get("payload")
    if not isinstance(body, dict):
        return None
    wrapped = body.get(name)
    if not isinstance(wrapped, dict):
        return None
    entity = wrapped.get("entity")
    if not isinstance(entity, dict):
        return None
    return entity


def safe_id(entity: Mapping[str, Any] | None, *keys: str) -> str | None:
    if entity is None:
        return None
    for key in keys:
        value = str(entity.get(key) or "").strip()
        if value:
            return value
    return None


def unix_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


class ChargeRecorder:
    """Upsert recurring charges from verified webhook identifiers + provider GET."""

    def __init__(self, charges: Any, subscriptions: Any, service: Any) -> None:
        self._charges = charges
        self._subscriptions = subscriptions
        self._service = service

    def record_charged_payload(self, payload: Mapping[str, Any], local: Any) -> None:
        if self._charges is None:
            return
        payment = payload_entity(payload, "payment")
        payment_id = safe_id(payment, "id")
        if not payment_id:
            return
        invoice_id = safe_id(payment, "invoice_id")
        amount = _optional_int(payment.get("amount") if payment is not None else None)
        currency = _optional_str(payment.get("currency") if payment is not None else None)
        pay_status = _optional_str(payment.get("status") if payment is not None else None)
        start = None
        end = None
        sub_id = getattr(local, "provider_subscription_id", None)
        if invoice_id:
            invoice = self._service.fetch_provider_invoice(invoice_id)
            invoice_id = invoice.id
            if invoice.subscription_id:
                sub_id = invoice.subscription_id
            if invoice.payment_id:
                payment_id = invoice.payment_id
            start = unix_datetime(invoice.billing_start)
            end = unix_datetime(invoice.billing_end)
            if invoice.amount is not None:
                amount = invoice.amount
            if invoice.currency:
                currency = invoice.currency
        self._charges.upsert_charge(
            provider_payment_id=payment_id,
            provider_invoice_id=invoice_id,
            provider_subscription_id=sub_id,
            user_subscription_id=getattr(local, "id", None),
            billing_period_start=start,
            billing_period_end=end,
            amount_paise=amount,
            currency=currency,
            payment_status=pay_status,
        )

    def apply_refund(self, payload: Mapping[str, Any]) -> tuple[str, str | None]:
        refund = payload_entity(payload, "refund")
        payment_entity = payload_entity(payload, "payment")
        refund_id = safe_id(refund, "id")
        payment_id = safe_id(refund, "payment_id") or safe_id(payment_entity, "id")
        if not payment_id:
            return "unmatched", None
        payment = self._service.fetch_provider_payment(payment_id)
        return self._upsert_from_payment(payment, last_refund_id=refund_id)

    def apply_dispute(self, payload: Mapping[str, Any]) -> tuple[str, str | None]:
        dispute_entity = payload_entity(payload, "dispute")
        dispute_id = safe_id(dispute_entity, "id")
        if not dispute_id:
            return "unmatched", None
        dispute = self._service.fetch_provider_dispute(dispute_id)
        payment_id = dispute.payment_id or safe_id(
            payload_entity(payload, "payment"), "id"
        )
        if not payment_id:
            return "unmatched", None
        payment = self._service.fetch_provider_payment(payment_id)
        return self._upsert_from_payment(
            payment,
            dispute_id=dispute.id,
            dispute_status=dispute.status,
        )

    def _upsert_from_payment(
        self,
        payment: ProviderPayment,
        *,
        last_refund_id: str | None = None,
        dispute_id: str | None = None,
        dispute_status: str | None = None,
    ) -> tuple[str, str | None]:
        resolved = self._resolve_from_payment(payment)
        if resolved is None:
            return "unmatched", None
        charge = self._charges.upsert_charge(
            provider_payment_id=payment.id,
            provider_invoice_id=resolved["invoice_id"],
            provider_subscription_id=resolved["provider_subscription_id"],
            user_subscription_id=resolved["user_subscription_id"],
            billing_period_start=resolved["billing_period_start"],
            billing_period_end=resolved["billing_period_end"],
            amount_paise=payment.amount,
            currency=payment.currency,
            payment_status=payment.status,
            refund_status=payment.refund_status,
            amount_refunded_paise=payment.amount_refunded,
            last_refund_id=last_refund_id,
            dispute_id=dispute_id,
            dispute_status=dispute_status,
        )
        return "processed", charge.provider_subscription_id

    def _resolve_from_payment(self, payment: ProviderPayment) -> dict[str, Any] | None:
        existing = self._charges.get_charge_by_payment_id(payment.id)
        if existing is not None:
            return {
                "invoice_id": existing.provider_invoice_id or payment.invoice_id,
                "provider_subscription_id": existing.provider_subscription_id,
                "user_subscription_id": existing.user_subscription_id,
                "billing_period_start": existing.billing_period_start,
                "billing_period_end": existing.billing_period_end,
            }
        invoice_id = payment.invoice_id
        if not invoice_id:
            return None
        invoice = self._service.fetch_provider_invoice(invoice_id)
        provider_sub_id = invoice.subscription_id
        if not provider_sub_id:
            return None
        local = self._subscriptions.get_subscription_by_provider_id(provider_sub_id)
        if local is None:
            return None
        return {
            "invoice_id": invoice.id,
            "provider_subscription_id": provider_sub_id,
            "user_subscription_id": local.id,
            "billing_period_start": unix_datetime(invoice.billing_start),
            "billing_period_end": unix_datetime(invoice.billing_end),
        }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
