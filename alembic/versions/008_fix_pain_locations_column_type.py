"""Fix pain_locations column type from TEXT to TEXT[]

The column was created as sa.Text() in migration 004 but the SQLAlchemy model
declares it as ARRAY(String). This caused the PostgreSQL array literal string
e.g. '{"Left Shoulder (Back)"}' to be stored in a TEXT column and then
iterated character-by-character when deserialised as a list.

Revision ID: 008_fix_pain_locations
Revises: 007_v20
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '008_fix_pain_locations'
down_revision = '007_v20'
branch_labels = None
depends_on = None


def upgrade():
    # The pain_locations column was created as TEXT in migration 004 but the
    # SQLAlchemy model declares it as ARRAY(String). SQLAlchemy wrote valid
    # PostgreSQL array literals (e.g. '{"Left Shoulder (Back)"}') into the TEXT
    # column. Casting to TEXT[] using ::TEXT[] correctly parses those literals.
    op.execute(
        """
        ALTER TABLE pain_logs
        ALTER COLUMN pain_locations
        TYPE TEXT[]
        USING CASE
            WHEN pain_locations IS NULL THEN NULL
            WHEN pain_locations = '' THEN '{}'::TEXT[]
            ELSE pain_locations::TEXT[]
        END
        """
    )


def downgrade():
    op.alter_column(
        'pain_logs',
        'pain_locations',
        type_=sa.Text(),
        postgresql_using='array_to_string(pain_locations, \',\')',
    )
