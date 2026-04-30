"""v19: add avatar_url to users

Revision ID: 006_v19
Revises: 005_v15
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = '006_v19'
down_revision = '005_v15'
branch_labels = None
depends_on = None


def upgrade():
    # Add avatar_url column to users table (nullable, safe to add)
    op.add_column('users', sa.Column('avatar_url', sa.String(2048), nullable=True))


def downgrade():
    op.drop_column('users', 'avatar_url')
