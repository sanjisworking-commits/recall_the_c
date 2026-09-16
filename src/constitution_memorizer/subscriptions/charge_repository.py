"""SQLite recurring charges. Payment id is the uniqueness key."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from constitution_memorizer.subscriptions.errors import InvalidSubscriptionValue
from constitution_memorizer.subscriptions.models import (
    PROVIDER_RAZORPAY,
    SubscriptionCharge,
    require_provider,
)
from constitution_memorizer.subscriptions.policy import (
    compute_charge_access_effect,
    require_access_effect,
    require_access_effect_reason,
)
from constitution_memorizer.subscriptions.repository import _dt_iso, _parse_dt, _utc_now

_SELECT = """
    SELECT id, provider, provider_payment_id, provider_invoice_id,
           provider_subscription_id, user_subscription_id,
           billing_period_start, billing_period_end, amount_paise, currency,
           payment_status, refund_status, amount_refunded_paise, last_refund_id,
           dispute_id, dispute_status, access_effect, access_effect_reason,
           access_effect_at, created_at, updated_at
    FROM subscription_charge
"""


def charge_from_mapping(row: Mapping[str, Any]) -> SubscriptionCharge:
    amount = row["amount_paise"]
    refunded = row["amount_refunded_paise"]
    return SubscriptionCharge(
        id=str(row["id"]),
        provider=str(row["provider"]),
        provider_payment_id=str(row["provider_payment_id"]),
        provider_invoice_id=row["provider_invoice_id"],
        provider_subscription_id=row["provider_subscription_id"],
        user_subscription_id=(
            str(row["user_subscription_id"])
            if row["user_subscription_id"] is not None
            else None
        ),
        billing_period_start=_parse_dt(row["billing_period_start"]),
        billing_period_end=_parse_dt(row["billing_period_end"]),
        amount_paise=int(amount) if amount is not None else None,
        currency=row["currency"],
        payment_status=row["payment_status"],
        refund_status=row["refund_status"],
        amount_refunded_paise=int(refunded or 0),
        last_refund_id=row["last_refund_id"],
        dispute_id=row["dispute_id"],
        dispute_status=row["dispute_status"],
        access_effect=str(row["access_effect"]),
        access_effect_reason=row["access_effect_reason"],
        access_effect_at=_parse_dt(row["access_effect_at"]),
        created_at=_parse_dt(row["created_at"]) or _utc_now(),
        updated_at=_parse_dt(row["updated_at"]) or _utc_now(),
    )


class SqliteChargeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_charge_by_payment_id(
        self,
        provider_payment_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> SubscriptionCharge | None:
        row = self.conn.execute(
            _SELECT + " WHERE provider = ? AND provider_payment_id = ?",
            (require_provider(provider), provider_payment_id),
        ).fetchone()
        if row is None:
            return None
        return charge_from_mapping(row)

    def list_charges_for_subscription(
        self, user_subscription_id: str
    ) -> list[SubscriptionCharge]:
        rows = self.conn.execute(
            _SELECT + " WHERE user_subscription_id = ? ORDER BY created_at ASC",
            (user_subscription_id,),
        ).fetchall()
        return [charge_from_mapping(row) for row in rows]

    def upsert_charge(
        self,
        *,
        provider_payment_id: str,
        provider: str = PROVIDER_RAZORPAY,
        provider_invoice_id: str | None = None,
        provider_subscription_id: str | None = None,
        user_subscription_id: str | None = None,
        billing_period_start: datetime | None = None,
        billing_period_end: datetime | None = None,
        amount_paise: int | None = None,
        currency: str | None = None,
        payment_status: str | None = None,
        refund_status: str | None = None,
        amount_refunded_paise: int | None = None,
        last_refund_id: str | None = None,
        dispute_id: str | None = None,
        dispute_status: str | None = None,
    ) -> SubscriptionCharge:
        payment_id = str(provider_payment_id or "").strip()
        if not payment_id:
            raise InvalidSubscriptionValue("provider payment id is required")
        existing = self.get_charge_by_payment_id(payment_id, provider=provider)
        now = _utc_now()
        merged = _merge_charge_fields(
            existing,
            provider_invoice_id=provider_invoice_id,
            provider_subscription_id=provider_subscription_id,
            user_subscription_id=user_subscription_id,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            amount_paise=amount_paise,
            currency=currency,
            payment_status=payment_status,
            refund_status=refund_status,
            amount_refunded_paise=amount_refunded_paise,
            last_refund_id=last_refund_id,
            dispute_id=dispute_id,
            dispute_status=dispute_status,
        )
        effect, reason = compute_charge_access_effect(
            merged["refund_status"], merged["dispute_status"]
        )
        require_access_effect(effect)
        require_access_effect_reason(reason)
        effect_at = merged["access_effect_at"]
        if effect == "period_ended" and (
            existing is None or existing.access_effect != "period_ended"
        ):
            effect_at = now
        if effect == "none":
            effect_at = None
        if existing is None:
            row_id = str(uuid4())
            try:
                self.conn.execute(
                    """
                    INSERT INTO subscription_charge (
                        id, provider, provider_payment_id, provider_invoice_id,
                        provider_subscription_id, user_subscription_id,
                        billing_period_start, billing_period_end, amount_paise,
                        currency, payment_status, refund_status,
                        amount_refunded_paise, last_refund_id, dispute_id,
                        dispute_status, access_effect, access_effect_reason,
                        access_effect_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        require_provider(provider),
                        payment_id,
                        merged["provider_invoice_id"],
                        merged["provider_subscription_id"],
                        merged["user_subscription_id"],
                        _dt_iso(merged["billing_period_start"]),
                        _dt_iso(merged["billing_period_end"]),
                        merged["amount_paise"],
                        merged["currency"],
                        merged["payment_status"],
                        merged["refund_status"],
                        int(merged["amount_refunded_paise"] or 0),
                        merged["last_refund_id"],
                        merged["dispute_id"],
                        merged["dispute_status"],
                        effect,
                        reason,
                        _dt_iso(effect_at),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                return self.upsert_charge(
                    provider_payment_id=payment_id,
                    provider=provider,
                    provider_invoice_id=provider_invoice_id,
                    provider_subscription_id=provider_subscription_id,
                    user_subscription_id=user_subscription_id,
                    billing_period_start=billing_period_start,
                    billing_period_end=billing_period_end,
                    amount_paise=amount_paise,
                    currency=currency,
                    payment_status=payment_status,
                    refund_status=refund_status,
                    amount_refunded_paise=amount_refunded_paise,
                    last_refund_id=last_refund_id,
                    dispute_id=dispute_id,
                    dispute_status=dispute_status,
                )
        else:
            self.conn.execute(
                """
                UPDATE subscription_charge
                SET provider_invoice_id = ?,
                    provider_subscription_id = ?,
                    user_subscription_id = ?,
                    billing_period_start = ?,
                    billing_period_end = ?,
                    amount_paise = ?,
                    currency = ?,
                    payment_status = ?,
                    refund_status = ?,
                    amount_refunded_paise = ?,
                    last_refund_id = ?,
                    dispute_id = ?,
                    dispute_status = ?,
                    access_effect = ?,
                    access_effect_reason = ?,
                    access_effect_at = ?,
                    updated_at = ?
                WHERE provider = ? AND provider_payment_id = ?
                """,
                (
                    merged["provider_invoice_id"],
                    merged["provider_subscription_id"],
                    merged["user_subscription_id"],
                    _dt_iso(merged["billing_period_start"]),
                    _dt_iso(merged["billing_period_end"]),
                    merged["amount_paise"],
                    merged["currency"],
                    merged["payment_status"],
                    merged["refund_status"],
                    int(merged["amount_refunded_paise"] or 0),
                    merged["last_refund_id"],
                    merged["dispute_id"],
                    merged["dispute_status"],
                    effect,
                    reason,
                    _dt_iso(effect_at),
                    now.isoformat(),
                    require_provider(provider),
                    payment_id,
                ),
            )
            self.conn.commit()
        stored = self.get_charge_by_payment_id(payment_id, provider=provider)
        assert stored is not None
        return stored


def _merge_charge_fields(existing: SubscriptionCharge | None, **incoming: Any) -> dict[str, Any]:
    def pick(name: str, default: Any = None) -> Any:
        value = incoming.get(name)
        if value is not None and value != "":
            return value
        if existing is None:
            return default
        return getattr(existing, name)

    return {
        "provider_invoice_id": pick("provider_invoice_id"),
        "provider_subscription_id": pick("provider_subscription_id"),
        "user_subscription_id": pick("user_subscription_id"),
        "billing_period_start": pick("billing_period_start"),
        "billing_period_end": pick("billing_period_end"),
        "amount_paise": pick("amount_paise"),
        "currency": pick("currency"),
        "payment_status": pick("payment_status"),
        "refund_status": pick("refund_status"),
        "amount_refunded_paise": pick("amount_refunded_paise", 0),
        "last_refund_id": pick("last_refund_id"),
        "dispute_id": pick("dispute_id"),
        "dispute_status": pick("dispute_status"),
        "access_effect_at": existing.access_effect_at if existing is not None else None,
    }
