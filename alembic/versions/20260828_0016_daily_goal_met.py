"""Daily-goal-met facts: one row per user per local date.

Revision ID: 20260828_0016
Revises: 20260827_0015
Create Date: 2026-08-28

Stores that the day's required study path was genuinely completed. Streak is
derived from consecutive dates — there is no incrementing streak column.
"""

from __future__ import annotations

from alembic import op

revision = "20260828_0016"
down_revision = "20260827_0015"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_goal_met (
    user_id UUID NOT NULL,
    goal_date DATE NOT NULL,
    met_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, goal_date)
);
"""

RLS = """
ALTER TABLE IF EXISTS daily_goal_met ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS daily_goal_met;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
