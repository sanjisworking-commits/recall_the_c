"""Learning plan preference + unique study-session day key.

Revision ID: 20260827_0014
Revises: 20260825_0013
Create Date: 2026-08-27

``user_learning_plan`` stores Self-paced vs Auto 3/5/7. It is not a queue.

``study_session`` already holds revision / auto_learning / day_plan snapshots.
A unique (user_id, kind, plan_date) index makes create-or-get atomic. Duplicate
historical rows, if any, keep the oldest session and drop the rest so the
index can land.
"""

from __future__ import annotations

from alembic import op

revision = "20260827_0014"
down_revision = "20260825_0013"
branch_labels = None
depends_on = None

PLAN_TABLE = """
CREATE TABLE IF NOT EXISTS user_learning_plan (
    user_id UUID PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'self_paced'
        CONSTRAINT user_learning_plan_mode_check
        CHECK (mode IN ('self_paced', 'auto')),
    daily_target INTEGER NULL
        CONSTRAINT user_learning_plan_target_check
        CHECK (daily_target IS NULL OR daily_target IN (3, 5, 7)),
    activated_at DATE NULL,
    prompt_dismissed_on DATE NULL,
    last_anchor_theme TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_learning_plan_auto_target_check
        CHECK (
            (mode = 'self_paced')
            OR (mode = 'auto' AND daily_target IS NOT NULL)
        )
);
"""

DEDUPE = """
DELETE FROM study_session_item
WHERE session_id IN (
    SELECT s.id
    FROM study_session s
    WHERE EXISTS (
        SELECT 1
        FROM study_session k
        WHERE k.user_id = s.user_id
          AND k.kind = s.kind
          AND k.plan_date = s.plan_date
          AND (
              k.created_at < s.created_at
              OR (k.created_at = s.created_at AND k.id < s.id)
          )
    )
);

DELETE FROM study_session s
WHERE EXISTS (
    SELECT 1
    FROM study_session k
    WHERE k.user_id = s.user_id
      AND k.kind = s.kind
      AND k.plan_date = s.plan_date
      AND (
          k.created_at < s.created_at
          OR (k.created_at = s.created_at AND k.id < s.id)
      )
);
"""

UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_study_session_user_kind_date
    ON study_session (user_id, kind, plan_date);
"""

RLS = """
ALTER TABLE IF EXISTS user_learning_plan ENABLE ROW LEVEL SECURITY;
"""

DOWNGRADE = """
DROP INDEX IF EXISTS idx_study_session_user_kind_date;
DROP TABLE IF EXISTS user_learning_plan;
"""


def upgrade() -> None:
    op.execute(PLAN_TABLE)
    op.execute(DEDUPE)
    op.execute(UNIQUE_INDEX)
    op.execute(RLS)


def downgrade() -> None:
    op.execute(DOWNGRADE)
