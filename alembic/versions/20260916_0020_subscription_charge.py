"""Subscription charge rows. Recurring payment linkage for refunds and disputes."""

from __future__ import annotations

from alembic import op

revision = "20260916_0020"
down_revision = "20260915_0019"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_charge (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL
        CONSTRAINT subscription_charge_provider_check
            CHECK (provider IN ('razorpay')),
    provider_payment_id TEXT NOT NULL,
    provider_invoice_id TEXT,
    provider_subscription_id TEXT,
    user_subscription_id UUID,
    billing_period_start TIMESTAMPTZ,
    billing_period_end TIMESTAMPTZ,
    amount_paise INTEGER,
    currency TEXT,
    payment_status TEXT,
    refund_status TEXT,
    amount_refunded_paise INTEGER NOT NULL DEFAULT 0
        CONSTRAINT subscription_charge_refunded_check CHECK (amount_refunded_paise >= 0),
    last_refund_id TEXT,
    dispute_id TEXT,
    dispute_status TEXT,
    access_effect TEXT NOT NULL DEFAULT 'none'
        CONSTRAINT subscription_charge_effect_check
            CHECK (access_effect IN ('none', 'period_ended')),
    access_effect_reason TEXT
        CONSTRAINT subscription_charge_reason_check CHECK (
            access_effect_reason IS NULL
            OR access_effect_reason IN ('full_refund', 'dispute_lost')
        ),
    access_effect_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS subscription_charge_provider_payment
    ON subscription_charge (provider, provider_payment_id);

CREATE INDEX IF NOT EXISTS subscription_charge_provider_sub
    ON subscription_charge (provider_subscription_id);

CREATE INDEX IF NOT EXISTS subscription_charge_user_sub
    ON subscription_charge (user_subscription_id);
"""

RLS = """
ALTER TABLE IF EXISTS subscription_charge ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS subscription_charge;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
