"""Monthly Playground roster period and roster-item tables.

Revision ID: 20260917_0024
Revises: 20260917_0023

Overlay tables (item / selection / progress) remain lifetime learning history.
These tables are the current Playground month only. They are not a lifetime
law entitlement. RLS is enabled with no policies: the app role bypasses RLS;
isolation is application-level user_id scoping.
"""

from __future__ import annotations

from alembic import op

revision = "20260917_0024"
down_revision = "20260917_0023"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_playground_period (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    tier_snapshot TEXT,
    law_limit INTEGER,
    status TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_playground_period_user_start UNIQUE (user_id, period_start),
    CONSTRAINT user_playground_period_status_check
        CHECK (status IN ('draft', 'active', 'closed'))
);

CREATE INDEX IF NOT EXISTS user_playground_period_user
    ON user_playground_period (user_id);

CREATE TABLE IF NOT EXISTS user_playground_roster_item (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    period_start DATE NOT NULL,
    law_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    carried_from_previous_period BOOLEAN NOT NULL DEFAULT false,
    consumed_at TIMESTAMPTZ,
    removed_at TIMESTAMPTZ,
    declined_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_playground_roster_item_user_period_law
        UNIQUE (user_id, period_start, law_id),
    CONSTRAINT user_playground_roster_item_origin_check
        CHECK (origin IN ('new', 're_add', 'carry_forward'))
);

CREATE INDEX IF NOT EXISTS user_playground_roster_item_user_period
    ON user_playground_roster_item (user_id, period_start);
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_period ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_playground_roster_item ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_playground_roster_item;
DROP TABLE IF EXISTS user_playground_period;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
