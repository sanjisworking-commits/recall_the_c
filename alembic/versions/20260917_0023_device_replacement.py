"""Playground device-replacement events for rolling churn policy.

Revision ID: 20260917_0023
Revises: 20260917_0022
"""

from __future__ import annotations

from alembic import op

revision = "20260917_0023"
down_revision = "20260917_0022"
branch_labels = None
depends_on = None

# First-class replacement history. Does not store installation cookies, HMAC,
# IP, fingerprints, or session tokens. 0021 and 0022 are unchanged.
SCHEMA = """
CREATE TABLE IF NOT EXISTS user_device_replacement (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    revoked_device_id UUID NOT NULL REFERENCES user_device(id),
    replacement_device_id UUID NOT NULL REFERENCES user_device(id),
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    platform TEXT
);

CREATE INDEX IF NOT EXISTS user_device_replacement_user_occurred
    ON user_device_replacement (user_id, occurred_at);
"""

RLS = """
ALTER TABLE IF EXISTS user_device_replacement ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_device_replacement;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
