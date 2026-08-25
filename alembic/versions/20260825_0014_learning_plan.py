"""User learning-plan preference (self-paced vs Auto 3/5/7).

Revision ID: 20260825_0014
Revises: 20260825_0013
Create Date: 2026-08-25

Study sessions already landed on main as 0013. This revision adds only the
planner preference row that 0013 did not introduce.
"""

from __future__ import annotations

from alembic import op

revision = "20260825_0014"
down_revision = "20260825_0013"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_learning_plan (
    user_id UUID PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'self_paced'
        CONSTRAINT user_learning_plan_mode_check
        CHECK (mode IN ('self_paced', 'auto')),
    daily_target INTEGER
        CONSTRAINT user_learning_plan_target_check
        CHECK (daily_target IS NULL OR daily_target IN (3, 5, 7)),
    activated_at DATE,
    plan_prompt_dismissed_on DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

RLS = """
ALTER TABLE IF EXISTS user_learning_plan ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_learning_plan;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
