"""Postgres recurring charges. Isolation is application-level."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
from constitution_memorizer.subscriptions.charge_repository import (
    _merge_charge_fields,
    access_effect_for_billing_period,
    charge_from_mapping,
)
from constitution_memorizer.subscriptions.repository import _utc_now

try:
    from psycopg.errors import CheckViolation, UniqueViolation
except ImportError:  # pragma: no cover
    class UniqueViolation(Exception):
        pass

    class CheckViolation(Exception):
        pass

_SELECT = """
    SELECT id, provider, provider_payment_id, provider_invoice_id,
           provider_subscription_id, user_subscription_id,
           billing_period_start, billing_period_end, amount_paise, currency,
           payment_status, refund_status, amount_refunded_paise, last_refund_id,
           dispute_id, dispute_status, access_effect, access_effect_reason,
           access_effect_at, created_at, updated_at
    FROM subscription_charge
"""


class PostgresChargeRepository:
    def __init__(self, pool: Any) -> None:
        from psycopg.rows import dict_row

        self._pool = pool
        self._dict_row = dict_row

    def _one(self, sql: str, params: tuple[Any, ...]) -> SubscriptionCharge | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
        if row is None:
            return None
        return charge_from_mapping(row)

    def get_charge_by_payment_id(
        self,
        provider_payment_id: str,
        *,
        provider: str = PROVIDER_RAZORPAY,
    ) -> SubscriptionCharge | None:
        return self._one(
            _SELECT + " WHERE provider = %s AND provider_payment_id = %s",
            (require_provider(provider), provider_payment_id),
        )

    def list_charges_for_subscription(
        self, user_subscription_id: str
    ) -> list[SubscriptionCharge]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=self._dict_row) as cur:
                cur.execute(
                    _SELECT
                    + " WHERE user_subscription_id = %s ORDER BY created_at ASC",
                    (user_subscription_id,),
                )
                rows = cur.fetchall()
        return [charge_from_mapping(row) for row in rows]

    def get_charge_access_effect_for_billing_period(
        self,
        user_subscription_id: str,
        billing_period_start: datetime,
        billing_period_end: datetime,
    ) -> str | None:
        return access_effect_for_billing_period(
            self.list_charges_for_subscription(user_subscription_id),
            billing_period_start,
            billing_period_end,
        )

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
        try:
            if existing is None:
                row_id = str(uuid4())
                with self._pool.connection() as conn:
                    with conn.cursor(row_factory=self._dict_row) as cur:
                        cur.execute(
                            """
                            INSERT INTO subscription_charge (
                                id, provider, provider_payment_id, provider_invoice_id,
                                provider_subscription_id, user_subscription_id,
                                billing_period_start, billing_period_end, amount_paise,
                                currency, payment_status, refund_status,
                                amount_refunded_paise, last_refund_id, dispute_id,
                                dispute_status, access_effect, access_effect_reason,
                                access_effect_at, created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            RETURNING id, provider, provider_payment_id,
                                      provider_invoice_id, provider_subscription_id,
                                      user_subscription_id, billing_period_start,
                                      billing_period_end, amount_paise, currency,
                                      payment_status, refund_status,
                                      amount_refunded_paise, last_refund_id,
                                      dispute_id, dispute_status, access_effect,
                                      access_effect_reason, access_effect_at,
                                      created_at, updated_at
                            """,
                            (
                                row_id,
                                require_provider(provider),
                                payment_id,
                                merged["provider_invoice_id"],
                                merged["provider_subscription_id"],
                                merged["user_subscription_id"],
                                merged["billing_period_start"],
                                merged["billing_period_end"],
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
                                effect_at,
                                now,
                                now,
                            ),
                        )
                        row = cur.fetchone()
                        conn.commit()
                assert row is not None
                return charge_from_mapping(row)
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=self._dict_row) as cur:
                    cur.execute(
                        """
                        UPDATE subscription_charge
                        SET provider_invoice_id = %s,
                            provider_subscription_id = %s,
                            user_subscription_id = %s,
                            billing_period_start = %s,
                            billing_period_end = %s,
                            amount_paise = %s,
                            currency = %s,
                            payment_status = %s,
                            refund_status = %s,
                            amount_refunded_paise = %s,
                            last_refund_id = %s,
                            dispute_id = %s,
                            dispute_status = %s,
                            access_effect = %s,
                            access_effect_reason = %s,
                            access_effect_at = %s,
                            updated_at = %s
                        WHERE provider = %s AND provider_payment_id = %s
                        RETURNING id, provider, provider_payment_id,
                                  provider_invoice_id, provider_subscription_id,
                                  user_subscription_id, billing_period_start,
                                  billing_period_end, amount_paise, currency,
                                  payment_status, refund_status,
                                  amount_refunded_paise, last_refund_id,
                                  dispute_id, dispute_status, access_effect,
                                  access_effect_reason, access_effect_at,
                                  created_at, updated_at
                        """,
                        (
                            merged["provider_invoice_id"],
                            merged["provider_subscription_id"],
                            merged["user_subscription_id"],
                            merged["billing_period_start"],
                            merged["billing_period_end"],
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
                            effect_at,
                            now,
                            require_provider(provider),
                            payment_id,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
        except UniqueViolation:
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
        except CheckViolation as exc:
            raise InvalidSubscriptionValue(
                "charge row failed a database check"
            ) from exc
        if row is None:
            raise InvalidSubscriptionValue("charge not found")
        return charge_from_mapping(row)
