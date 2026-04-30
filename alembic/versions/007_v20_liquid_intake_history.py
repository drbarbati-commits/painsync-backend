"""v20: enrich water_logs for liquid intake history editing

Revision ID: 007_v20
Revises: 006_v19
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = '007_v20'
down_revision = '006_v19'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('water_logs', sa.Column('drink_type', sa.String(length=100), nullable=True))
    op.add_column('water_logs', sa.Column('is_alcoholic', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('water_logs', sa.Column('abv', sa.Float(), nullable=True))
    op.add_column('water_logs', sa.Column('alcohol_units', sa.Float(), nullable=True))
    op.add_column('water_logs', sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('water_logs', 'notes')
    op.drop_column('water_logs', 'alcohol_units')
    op.drop_column('water_logs', 'abv')
    op.drop_column('water_logs', 'is_alcoholic')
    op.drop_column('water_logs', 'drink_type')
