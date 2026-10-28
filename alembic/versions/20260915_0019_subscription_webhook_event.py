"""Subscription webhook event log. Not a user-owned entitlement table.

Revision ID: 20260915_0019
Revises: 20260911_0018
Create Date: 2026-09-15

Stores Razorpay event-id reservations for idempotent webhook processing.
Does not store raw payment/card payloads. RLS enabled with no policies:
the app role bypasses RLS; isolation is application-level.
"""

from __future__ import annotations

from alembic import op

revision = "20260915_0019"
down_revision = "20260911_0018"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_webhook_event (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL
        CONSTRAINT subscription_webhook_event_provider_check
            CHECK (provider IN ('razorpay')),
    provider_event_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    provider_subscription_id TEXT,
    event_created_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    payload_sha256 TEXT NOT NULL,
    processing_status TEXT NOT NULL
        CONSTRAINT subscription_webhook_event_status_check CHECK (processing_status IN (
            'processing', 'processed', 'ignored', 'failed', 'unmatched'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 1
        CONSTRAINT subscription_webhook_event_attempt_check CHECK (attempt_count >= 1),
    processed_at TIMESTAMPTZ,
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS subscription_webhook_event_provider_event
    ON subscription_webhook_event (provider, provider_event_id);

CREATE INDEX IF NOT EXISTS subscription_webhook_event_status_received
    ON subscription_webhook_event (processing_status, received_at DESC);

CREATE INDEX IF NOT EXISTS subscription_webhook_event_provider_sub
    ON subscription_webhook_event (provider_subscription_id);
"""

RLS = """
ALTER TABLE IF EXISTS subscription_webhook_event ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS subscription_webhook_event;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
