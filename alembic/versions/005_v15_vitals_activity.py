"""v15: add body_temp and weight to pain_log, add activity_logs table
Revision ID: 005_v15
Revises: 004_v14
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '005_v15'
down_revision = '004_v14'
branch_labels = None
depends_on = None


def upgrade():
    # ── Pain log: vitals at time of logging ──────────────────────────────────
    op.add_column('pain_logs', sa.Column('body_temp_celsius', sa.Float(), nullable=True))
    op.add_column('pain_logs', sa.Column('weight_at_log_kg', sa.Float(), nullable=True))

    # ── Activity logs table ──────────────────────────────────────────────────
    op.create_table(
        'activity_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('steps', sa.Integer(), nullable=True),
        sa.Column('distance_km', sa.Float(), nullable=True),
        sa.Column('active_minutes', sa.Integer(), nullable=True),
        sa.Column('calories_burned', sa.Float(), nullable=True),
        sa.Column('activity_type', sa.String(100), nullable=True),  # walking, running, cycling…
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(50), nullable=True, server_default='manual'),  # manual | healthkit | gps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('activity_logs')
    op.drop_column('pain_logs', 'weight_at_log_kg')
    op.drop_column('pain_logs', 'body_temp_celsius')
