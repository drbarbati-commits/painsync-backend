"""Add device_token and device_platform to users

Revision ID: 009_add_device_token
Revises: 008_fix_pain_locations
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = '009_add_device_token'
down_revision = '008_fix_pain_locations'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('device_token', sa.String(512), nullable=True))
    op.add_column('users', sa.Column('device_platform', sa.String(10), nullable=True))


def downgrade():
    op.drop_column('users', 'device_platform')
    op.drop_column('users', 'device_token')
