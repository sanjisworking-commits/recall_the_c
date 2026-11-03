"""Permanent Free-choice ledger (tier-revision plan B1, decisions 5-9a / 5-21 M0).

Revision ID: 20261103_0028
Revises: 20260927_0027

One row per (account, law) the account has ever chosen as a Free Playground
law. Rows are never deleted or rewritten by the application: removal of a
law from the roster leaves its ledger row (re-add is free), and no
subscription event, reconciliation, flag flip or downgrade touches it.

M0: schema only. No row is derived from ``user_playground_period``,
``user_playground_roster_item`` or ``user_free_articles``. Re-running is a
no-op (``IF NOT EXISTS``); an environment where the table already holds
rows is left exactly as it is.

RLS is enabled with no policies: the app role bypasses RLS; isolation is
application-level user_id scoping (same convention as 0024–0027).
"""

from __future__ import annotations

from alembic import op

revision = "20261103_0028"
down_revision = "20260927_0027"
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_playground_choice (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    law_id TEXT NOT NULL,
    chosen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'free_add',
    CONSTRAINT user_playground_choice_user_law UNIQUE (user_id, law_id),
    CONSTRAINT user_playground_choice_source_check
        CHECK (source IN ('free_add'))
);

CREATE INDEX IF NOT EXISTS user_playground_choice_user
    ON user_playground_choice (user_id);
"""

RLS = """
ALTER TABLE IF EXISTS user_playground_choice
    ENABLE ROW LEVEL SECURITY;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    op.execute(RLS)


def downgrade() -> None:
    """Refused on purpose (plan §4.7 rule 1).

    Dropping the permanent-choice ledger is never part of a rollback: a flag
    deactivation keeps the rows, and a version rollback runs the previous
    application against this schema (the old code ignores the table). The
    table is dropped only after the owner separately confirms abandonment
    and an export has been taken, by a dedicated migration or by hand.
    """

    raise RuntimeError(
        "user_playground_choice is retained: the permanent-choice ledger is not "
        "dropped by alembic downgrade. Export it and drop it deliberately."
    )
