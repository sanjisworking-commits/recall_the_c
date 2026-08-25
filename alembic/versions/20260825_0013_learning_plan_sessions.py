"""Learning plan preferences and study sessions.

Revision ID: 20260825_0013
Revises: 20260821_0012
Create Date: 2026-08-25
"""

from __future__ import annotations

from alembic import op

revision = "20260825_0013"
down_revision = "20260821_0012"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_learning_plan (
    user_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'self_paced'
        CHECK (mode IN ('self_paced', 'auto')),
    daily_target INTEGER CHECK (daily_target IS NULL OR daily_target IN (3, 5, 7)),
    activated_at DATE,
    plan_prompt_dismissed_on DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS study_session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('revision', 'auto_learning', 'one_day_learning')),
    plan_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'abandoned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_session_one_active_revision
    ON study_session(user_id)
    WHERE status = 'active' AND kind = 'revision';

CREATE UNIQUE INDEX IF NOT EXISTS idx_study_session_one_active_learning
    ON study_session(user_id, plan_date)
    WHERE status = 'active' AND kind IN ('auto_learning', 'one_day_learning');

CREATE INDEX IF NOT EXISTS idx_study_session_user_date
    ON study_session(user_id, plan_date, status);

CREATE TABLE IF NOT EXISTS study_session_item (
    session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    learning_unit_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'completed', 'deferred')),
    completed_at TIMESTAMPTZ,
    deferred_at TIMESTAMPTZ,
    PRIMARY KEY (session_id, position),
    FOREIGN KEY (session_id) REFERENCES study_session(id) ON DELETE CASCADE,
    UNIQUE (session_id, learning_unit_id)
);

CREATE INDEX IF NOT EXISTS idx_study_session_item_session
    ON study_session_item(session_id, state);
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute("ALTER TABLE IF EXISTS user_learning_plan ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS study_session ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE IF EXISTS study_session_item ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_study_session_item_session;
        DROP TABLE IF EXISTS study_session_item;
        DROP INDEX IF EXISTS idx_study_session_user_date;
        DROP INDEX IF EXISTS idx_study_session_one_active_learning;
        DROP INDEX IF EXISTS idx_study_session_one_active_revision;
        DROP TABLE IF EXISTS study_session;
        DROP TABLE IF EXISTS user_learning_plan;
        """
    )
