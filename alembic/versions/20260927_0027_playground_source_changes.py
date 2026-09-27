"""Playground source-change review.

Revision ID: 20260927_0027
Revises: 20260925_0026

Per-provision amendment facts live in ``user_playground_source_change``.
A compact law-level scan row remembers the last targeted comparison for a
registry identity so home can show persisted affected counts without
hydrating Acts. Historical learning rows are not rewritten.

RLS is enabled with no policies: the app role bypasses RLS; isolation is
application-level user_id scoping.
"""

from __future__ import annotations

from alembic import op

revision = "20260927_0027"
down_revision = "20260925_0026"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_playground_source_change (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    detected_source_version TEXT NOT NULL,
    detected_law_source_hash TEXT NOT NULL,
    previous_source_version TEXT NOT NULL,
    previous_section_hash TEXT NOT NULL,
    current_source_version TEXT NOT NULL,
    current_law_source_hash TEXT NOT NULL,
    current_section_hash TEXT NOT NULL DEFAULT '',
    change_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    had_learning INTEGER NOT NULL DEFAULT 0,
    had_selection INTEGER NOT NULL DEFAULT 0,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        user_id,
        law_id,
        source_locator,
        current_source_version,
        current_law_source_hash
    ),
    CONSTRAINT user_playground_source_change_kind_check
        CHECK (change_kind IN ('changed', 'missing', 'omitted')),
    CONSTRAINT user_playground_source_change_status_check
        CHECK (status IN ('pending', 'reviewed'))
);

CREATE INDEX IF NOT EXISTS user_playground_source_change_user_law
    ON user_playground_source_change (user_id, law_id, status);

CREATE TABLE IF NOT EXISTS user_playground_source_scan (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    scanned_source_version TEXT NOT NULL,
    scanned_law_source_hash TEXT NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    affected_total INTEGER NOT NULL DEFAULT 0,
    affected_learned_count INTEGER NOT NULL DEFAULT 0,
    affected_selected_only_count INTEGER NOT NULL DEFAULT 0,
    unchanged_user_relevant_count INTEGER NOT NULL DEFAULT 0,
    missing_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (
        user_id,
        law_id,
        scanned_source_version,
        scanned_law_source_hash
    )
);

CREATE INDEX IF NOT EXISTS user_playground_source_scan_user_law
    ON user_playground_source_scan (user_id, law_id);
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_source_change
    ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_playground_source_scan
    ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP INDEX IF EXISTS user_playground_source_scan_user_law;
DROP TABLE IF EXISTS user_playground_source_scan;
DROP INDEX IF EXISTS user_playground_source_change_user_law;
DROP TABLE IF EXISTS user_playground_source_change;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
