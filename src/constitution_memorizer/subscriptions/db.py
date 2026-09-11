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
"""


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
