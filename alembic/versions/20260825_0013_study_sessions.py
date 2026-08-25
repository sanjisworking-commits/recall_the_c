"""Study sessions: a resumable, snapshotted queue of learning units.

Revision ID: 20260825_0013
Revises: 20260821_0012
Create Date: 2026-08-25

``mark_done`` decides what comes next from the static Constitution graph, so
finishing a due unit walks to its sequential neighbour rather than to the next
*due* unit. A session is the missing navigation context: a snapshot taken when
the user starts, walked to exhaustion, and resumable after they leave.

``kind`` is open from the start because revision is the first of three
queue-shaped features (revision, auto-learning, day plan) and they differ only
in how the snapshot is built.

``study_session_item.status`` is what makes "Again tomorrow" expressible: a
deferred item leaves the queue without being a completed revision, so the
count the dashboard reports stays honest.
"""

from __future__ import annotations

from alembic import op

revision = "20260825_0013"
down_revision = "20260821_0012"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS study_session (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    kind TEXT NOT NULL
        CONSTRAINT study_session_kind_check
        CHECK (kind IN ('revision', 'auto_learning', 'day_plan')),
    plan_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CONSTRAINT study_session_status_check
        CHECK (status IN ('active', 'complete')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS study_session_item (
    session_id TEXT NOT NULL
        REFERENCES study_session(id) ON DELETE CASCADE,
    learning_unit_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT study_session_item_status_check
        CHECK (status IN ('pending', 'completed', 'deferred')),
    completed_at TIMESTAMPTZ NULL,
    PRIMARY KEY (session_id, learning_unit_id)
);

CREATE INDEX IF NOT EXISTS idx_study_session_user_kind
    ON study_session(user_id, kind, status);
CREATE INDEX IF NOT EXISTS idx_study_session_item_order
    ON study_session_item(session_id, position);
"""

# Same end state as 0010/0012 assert for every other public table: the schema
# is served to the `anon` role through PostgREST, so a new table without RLS
# is a hole. If a later migration re-asserts the RLS list, these two belong
# in it.
RLS = """
ALTER TABLE IF EXISTS study_session ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS study_session_item ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP TABLE IF EXISTS study_session_item;
DROP TABLE IF EXISTS study_session;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
