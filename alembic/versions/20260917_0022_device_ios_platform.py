"""Allow iOS as a user_device platform.

Revision ID: 20260917_0022
Revises: 20260916_0021
"""

from __future__ import annotations

from alembic import op

revision = "20260917_0022"
down_revision = "20260916_0021"
branch_labels = None
depends_on = None

# Safe CHECK replacement only. Existing web/android rows stay valid.
# Do not rebuild user_device. Production authority is Postgres; 0021 is
# unchanged.
UPGRADE = """
ALTER TABLE user_device DROP CONSTRAINT IF EXISTS user_device_platform_check;
ALTER TABLE user_device
    ADD CONSTRAINT user_device_platform_check
    CHECK (platform IN ('web', 'android', 'ios'));
"""

DOWNGRADE = """
ALTER TABLE user_device DROP CONSTRAINT IF EXISTS user_device_platform_check;
ALTER TABLE user_device
    ADD CONSTRAINT user_device_platform_check
    CHECK (platform IN ('web', 'android'));
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
