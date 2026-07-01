"""New users start as free (subscription_status='none') instead of auto-trial

Revision ID: 010_default_sub_none
Revises: 009_add_device_token
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = '010_default_sub_none'
down_revision = '009_add_device_token'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'users', 'subscription_status',
        server_default='none',
    )
    # Existing accounts that were auto-defaulted into 'trial' but never
    # actually started a trial (no trial_started_at) were never really
    # trialing — correct them to the free tier.
    op.execute(
        "UPDATE users SET subscription_status = 'none' "
        "WHERE subscription_status = 'trial' AND trial_started_at IS NULL"
    )


def downgrade():
    op.alter_column(
        'users', 'subscription_status',
        server_default='trial',
    )
