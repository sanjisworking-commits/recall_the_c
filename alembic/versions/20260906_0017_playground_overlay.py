"""Playground overlay: user-owned NDPS/BNS learning state.

Revision ID: 20260906_0017
Revises: 20260828_0016
Create Date: 2026-09-06

Stores activation, section selection, and Cloze/revision progress against
verbatim Bare Act JSON. No statutory text is duplicated. RLS is enabled with
no policies: the app role bypasses RLS; isolation is application-level.
"""

from __future__ import annotations

from alembic import op

revision = "20260906_0017"
down_revision = "20260828_0016"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_playground_item (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_playground',
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_version TEXT NOT NULL,
    law_source_hash TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id)
);

CREATE TABLE IF NOT EXISTS user_playground_selection (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (user_id, law_id, source_locator)
);

CREATE TABLE IF NOT EXISTS user_playground_progress (
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    cloze_done INTEGER NOT NULL DEFAULT 0,
    times_completed INTEGER NOT NULL DEFAULT 0,
    last_completed DATE,
    next_revision DATE,
    interval_days INTEGER NOT NULL DEFAULT 0,
    source_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, law_id, source_locator)
);
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_playground_selection ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS user_playground_progress ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS user_playground_progress;
DROP TABLE IF EXISTS user_playground_selection;
DROP TABLE IF EXISTS user_playground_item;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
