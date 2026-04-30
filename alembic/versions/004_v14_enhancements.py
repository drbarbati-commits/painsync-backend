"""v14: add user profile fields, subscription, password reset, multi-location pain log, sleep sound
Revision ID: 004_v14
Revises: 003
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '004_v14'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # ── Users: new profile and subscription columns ──────────────────────────
    op.add_column('users', sa.Column('phone', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('weight_kg', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('height_cm', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('language', sa.String(10), nullable=True, server_default='en'))
    op.add_column('users', sa.Column('country', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('unit_weight', sa.String(10), nullable=True, server_default='kg'))
    op.add_column('users', sa.Column('unit_height', sa.String(10), nullable=True, server_default='cm'))
    op.add_column('users', sa.Column('unit_temperature', sa.String(10), nullable=True, server_default='celsius'))
    op.add_column('users', sa.Column('unit_volume', sa.String(10), nullable=True, server_default='ml'))
    op.add_column('users', sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('subscription_status', sa.String(50), nullable=True, server_default='trial'))
    op.add_column('users', sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True))

    # ── Password reset tokens table ──────────────────────────────────────────
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('token', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Pain logs: multi-location and duration in minutes ────────────────────
    op.add_column('pain_logs',
        sa.Column('pain_locations', sa.Text(), nullable=True))
    op.add_column('pain_logs',
        sa.Column('duration_minutes', sa.Float(), nullable=True))

    # ── Sleep logs: sound recording URL ─────────────────────────────────────
    op.add_column('sleep_logs',
        sa.Column('sound_recording_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('sleep_logs', 'sound_recording_url')
    op.drop_column('pain_logs', 'duration_minutes')
    op.drop_column('pain_logs', 'pain_locations')
    op.drop_table('password_reset_tokens')
    op.drop_column('users', 'subscription_expires_at')
    op.drop_column('users', 'subscription_status')
    op.drop_column('users', 'trial_started_at')
    op.drop_column('users', 'unit_volume')
    op.drop_column('users', 'unit_temperature')
    op.drop_column('users', 'unit_height')
    op.drop_column('users', 'unit_weight')
    op.drop_column('users', 'country')
    op.drop_column('users', 'language')
    op.drop_column('users', 'height_cm')
    op.drop_column('users', 'weight_kg')
    op.drop_column('users', 'phone')
