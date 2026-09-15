"""SQLite user_subscription overlay. Constitution and billing_orders are untouched."""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_subscription (
    id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL
        CHECK (provider IN ('razorpay')),
    provider_customer_id TEXT,
    provider_subscription_id TEXT,
    provider_plan_id TEXT,
    tier TEXT NOT NULL
        CHECK (tier IN ('plus', 'pro', 'max')),
    status TEXT NOT NULL
        CHECK (status IN (
            'created', 'authenticated', 'active', 'pending', 'halted',
            'paused', 'cancelled', 'completed', 'expired'
        )),
    billing_period_start TEXT,
    billing_period_end TEXT,
    cancel_at_period_end INTEGER NOT NULL DEFAULT 0
        CHECK (cancel_at_period_end IN (0, 1)),
    is_current INTEGER NOT NULL DEFAULT 1
        CHECK (is_current IN (0, 1)),
    provider_metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS user_subscription_one_current
    ON user_subscription (user_id) WHERE is_current = 1;

CREATE UNIQUE INDEX IF NOT EXISTS user_subscription_provider_sub_id
    ON user_subscription (provider, provider_subscription_id)
    WHERE provider_subscription_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS user_subscription_user_created
    ON user_subscription (user_id, created_at);

CREATE INDEX IF NOT EXISTS user_subscription_status_period
    ON user_subscription (status, billing_period_end);

CREATE TABLE IF NOT EXISTS subscription_webhook_event (
    id TEXT NOT NULL PRIMARY KEY,
    provider TEXT NOT NULL
        CHECK (provider IN ('razorpay')),
    provider_event_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    provider_subscription_id TEXT,
    event_created_at TEXT,
    received_at TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    processing_status TEXT NOT NULL
        CHECK (processing_status IN (
            'processing', 'processed', 'ignored', 'failed', 'unmatched'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 1
        CHECK (attempt_count >= 1),
    processed_at TEXT,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS subscription_webhook_event_provider_event
    ON subscription_webhook_event (provider, provider_event_id);

CREATE INDEX IF NOT EXISTS subscription_webhook_event_status_received
    ON subscription_webhook_event (processing_status, received_at);

CREATE INDEX IF NOT EXISTS subscription_webhook_event_provider_sub
    ON subscription_webhook_event (provider_subscription_id);
"""


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
