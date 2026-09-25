"""Playground Learned → revision lifecycle.

Revision ID: 20260925_0026
Revises: 20260924_0025

Adds ``learned_at`` on ``user_playground_progress`` and a separate
per-rung revision-mode table. Initial six-mode rows in
``user_playground_mode_progress`` stay lifetime evidence and are not
reset. RLS is enabled with no policies: the app role bypasses RLS;
isolation is application-level user_id scoping.

Does not invalidate Learned or Mastered on statute change (M9).
Does not rewrite Constitution reminder / calendar tables.
"""

from __future__ import annotations

from alembic import op

revision = "20260925_0026"
down_revision = "20260924_0025"
branch_labels = None
depends_on = None

SCHEMA = """
ALTER TABLE user_playground_progress
    ADD COLUMN IF NOT EXISTS learned_at DATE;

CREATE TABLE IF NOT EXISTS user_playground_revision_mode_progress (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    rung_days INTEGER NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    first_started_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, law_id, source_locator, rung_days, mode),
    CONSTRAINT user_playground_revision_mode_progress_rung_check
        CHECK (rung_days IN (1, 3, 7, 15, 30, 60)),
    CONSTRAINT user_playground_revision_mode_progress_mode_check
        CHECK (mode IN ('read', 'cloze', 'letters', 'type', 'recite', 'test')),
    CONSTRAINT user_playground_revision_mode_progress_status_check
        CHECK (status IN ('in_progress', 'completed'))
);

CREATE INDEX IF NOT EXISTS user_playground_progress_due
    ON user_playground_progress (user_id, next_revision, status);

CREATE INDEX IF NOT EXISTS user_playground_revision_mode_progress_user_law
    ON user_playground_revision_mode_progress (
        user_id, law_id, source_locator, rung_days
    );
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_revision_mode_progress
    ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP INDEX IF EXISTS user_playground_revision_mode_progress_user_law;
DROP INDEX IF EXISTS user_playground_progress_due;
DROP TABLE IF EXISTS user_playground_revision_mode_progress;
ALTER TABLE user_playground_progress DROP COLUMN IF EXISTS learned_at;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
