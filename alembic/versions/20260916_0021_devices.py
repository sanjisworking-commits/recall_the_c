"""Playground device registry: user_device + user_device_session.

Revision ID: 20260916_0021
Revises: 20260916_0020
"""

from __future__ import annotations

from alembic import op

revision = "20260916_0021"
down_revision = "20260916_0020"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_device (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    device_key_hash TEXT NOT NULL,
    platform TEXT NOT NULL
        CONSTRAINT user_device_platform_check
            CHECK (platform IN ('web', 'android')),
    display_name TEXT,
    first_registered_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_device_user_hash_key UNIQUE (user_id, device_key_hash)
);

CREATE INDEX IF NOT EXISTS user_device_user
    ON user_device (user_id);

CREATE INDEX IF NOT EXISTS user_device_user_active
    ON user_device (user_id, revoked_at);

CREATE TABLE IF NOT EXISTS user_device_session (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    device_id UUID NOT NULL REFERENCES user_device(id),
    auth_session_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT user_device_session_user_auth_key UNIQUE (user_id, auth_session_id)
);

CREATE INDEX IF NOT EXISTS user_device_session_device
    ON user_device_session (device_id);

CREATE INDEX IF NOT EXISTS user_device_session_user
    ON user_device_session (user_id);
"""

RLS = """
ALTER TABLE IF EXISTS user_device ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_device_session ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_device_session;
DROP TABLE IF EXISTS user_device;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
