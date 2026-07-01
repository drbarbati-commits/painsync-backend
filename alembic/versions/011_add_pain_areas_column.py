"""Add users.pain_areas column (TEXT[]) — was never migrated, only present
on prod via an out-of-band ALTER. Model declared it as plain Text, causing
asyncpg DatatypeMismatchError on every INSERT (VARCHAR vs TEXT[]).

Revision ID: 011_pain_areas
Revises: 010_default_sub_none
Create Date: 2026-07-01
"""
from alembic import op

revision = '011_pain_areas'
down_revision = '010_default_sub_none'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS pain_areas TEXT[]
        """
    )


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS pain_areas")
