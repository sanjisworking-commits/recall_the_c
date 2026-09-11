"""Playground commercial subscriptions: user_subscription history + one current.

Revision ID: 20260911_0018
Revises: 20260906_0017
Create Date: 2026-09-11

Additive to legacy billing_orders / access_grants. One current commercial
subscription per user via a partial unique index. Provider is an explicit
column (razorpay). RLS enabled with no policies: the app role bypasses RLS;
isolation is application-level.
"""

from __future__ import annotations

from alembic import op

revision = "20260911_0018"
down_revision = "20260906_0017"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_subscription (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    provider TEXT NOT NULL
        CONSTRAINT user_subscription_provider_check CHECK (provider IN ('razorpay')),
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    provider_plan_id TEXT,
    tier TEXT NOT NULL
        CONSTRAINT user_subscription_tier_check CHECK (tier IN ('plus', 'pro', 'max')),
    status TEXT NOT NULL
        CONSTRAINT user_subscription_status_check CHECK (status IN (
            'created', 'authenticated', 'active', 'pending', 'halted',
            'paused', 'cancelled', 'completed', 'expired'
        )),
    billing_period_start TIMESTAMPTZ,
    billing_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_subscription_one_current
    ON user_subscription (user_id) WHERE is_current;

CREATE UNIQUE INDEX IF NOT EXISTS user_subscription_provider_sub_id
    ON user_subscription (provider, provider_subscription_id)
    WHERE provider_subscription_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS user_subscription_user_created
    ON user_subscription (user_id, created_at);

CREATE INDEX IF NOT EXISTS user_subscription_status_period
    ON user_subscription (status, billing_period_end);
"""

RLS = """
ALTER TABLE IF EXISTS user_subscription ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_subscription;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
