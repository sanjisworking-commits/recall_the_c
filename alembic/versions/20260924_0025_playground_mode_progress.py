"""Playground per-mode learning progress.

Revision ID: 20260924_0025
Revises: 20260917_0024

Stores independent Read/Cloze/Letters/Type/Recite/Test completion against
verbatim Bare Act locators. No statutory text, typed attempts, transcripts,
or audio. RLS is enabled with no policies: the app role bypasses RLS;
isolation is application-level user_id scoping.

Does not rewrite ``user_playground_progress`` revision rows. Completing a
mode here does not start Day 1. M8 owns Learned → revision.
"""

from __future__ import annotations

from alembic import op

revision = "20260924_0025"
down_revision = "20260917_0024"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_playground_mode_progress (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
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
    PRIMARY KEY (user_id, law_id, source_locator, mode),
    CONSTRAINT user_playground_mode_progress_mode_check
        CHECK (mode IN ('read', 'cloze', 'letters', 'type', 'recite', 'test')),
    CONSTRAINT user_playground_mode_progress_status_check
        CHECK (status IN ('in_progress', 'completed'))
);

CREATE INDEX IF NOT EXISTS user_playground_mode_progress_user_law
    ON user_playground_mode_progress (user_id, law_id, source_locator);
"""

BACKFILL = """
INSERT INTO user_playground_mode_progress (
    user_id, law_id, source_locator, mode, status, attempt_count,
    first_started_at, last_attempt_at, completed_at,
    source_version, source_hash, created_at, updated_at
)
SELECT
    user_id,
    law_id,
    source_locator,
    'cloze',
    'completed',
    CASE WHEN times_completed < 1 THEN 1 ELSE times_completed END,
    COALESCE(updated_at, NOW()),
    COALESCE(updated_at, NOW()),
    COALESCE(last_completed::timestamptz, updated_at, NOW()),
    source_version,
    source_hash,
    COALESCE(updated_at, NOW()),
    COALESCE(updated_at, NOW())
FROM user_playground_progress
WHERE cloze_done != 0
ON CONFLICT (user_id, law_id, source_locator, mode) DO NOTHING;
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_mode_progress ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_playground_mode_progress;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(BACKFILL)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
