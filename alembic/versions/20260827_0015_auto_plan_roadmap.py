"""Persisted rolling Auto roadmap plus target_effective_on audit.

Revision ID: 20260827_0015
Revises: 20260827_0014
Create Date: 2026-08-27

``auto_plan_day`` / ``auto_plan_item`` store the mutable 15-calendar-day Auto
NEW assignment window. Historical rows stay as audit; there is no global
unique on learning_unit_id.

``user_learning_plan.target_effective_on`` records when the current Auto
daily_target became effective. Null on Self-paced. Not a history table.
"""

from __future__ import annotations

from alembic import op

revision = "20260827_0015"
down_revision = "20260827_0014"
branch_labels = None
depends_on = None

SCHEMA = """
ALTER TABLE user_learning_plan
    ADD COLUMN IF NOT EXISTS target_effective_on DATE NULL;

CREATE TABLE IF NOT EXISTS auto_plan_day (
    user_id UUID NOT NULL,
    plan_date DATE NOT NULL,
    daily_target INTEGER NOT NULL
        CONSTRAINT auto_plan_day_target_check
        CHECK (daily_target IN (3, 5, 7)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, plan_date)
);

CREATE TABLE IF NOT EXISTS auto_plan_item (
    user_id UUID NOT NULL,
    plan_date DATE NOT NULL,
    learning_unit_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, plan_date, learning_unit_id),
    CONSTRAINT auto_plan_item_day_fk
        FOREIGN KEY (user_id, plan_date)
        REFERENCES auto_plan_day(user_id, plan_date)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auto_plan_item_user_date_position
    ON auto_plan_item (user_id, plan_date, position);
"""

RLS = """
ALTER TABLE IF EXISTS auto_plan_day ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS auto_plan_item ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS auto_plan_item;
DROP TABLE IF EXISTS auto_plan_day;
ALTER TABLE user_learning_plan DROP COLUMN IF EXISTS target_effective_on;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
"""
