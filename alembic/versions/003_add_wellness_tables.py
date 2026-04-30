"""Add wellness tables: food_logs, water_logs, sleep_logs, pain_video_analyses

Revision ID: 003
Revises: 002
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # ── food_logs ────────────────────────────────────────────────────────────
    op.create_table(
        'food_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('meal_type', sa.String(50), nullable=True),
        sa.Column('before_photo_url', sa.Text(), nullable=True),
        sa.Column('after_photo_url', sa.Text(), nullable=True),
        sa.Column('food_description', sa.Text(), nullable=True),
        sa.Column('estimated_calories', sa.Float(), nullable=True),
        sa.Column('estimated_protein_g', sa.Float(), nullable=True),
        sa.Column('estimated_carbs_g', sa.Float(), nullable=True),
        sa.Column('estimated_fat_g', sa.Float(), nullable=True),
        sa.Column('intake_percentage', sa.Float(), nullable=True),
        sa.Column('ai_notes', sa.Text(), nullable=True),
        sa.Column('pain_level_during', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('logged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_food_logs_id', 'food_logs', ['id'])

    # ── water_logs ───────────────────────────────────────────────────────────
    op.create_table(
        'water_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('liquid_type', sa.String(100), nullable=False, server_default='water'),
        sa.Column('amount_ml', sa.Float(), nullable=False),
        sa.Column('logged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_water_logs_id', 'water_logs', ['id'])

    # ── sleep_logs (Flutter-aligned field names) ─────────────────────────────
    op.create_table(
        'sleep_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('bedtime', sa.String(5), nullable=True),       # "HH:MM"
        sa.Column('wake_time', sa.String(5), nullable=True),     # "HH:MM"
        sa.Column('duration_hours', sa.Float(), nullable=True),
        sa.Column('quality_rating', sa.Integer(), nullable=True), # 1-5
        sa.Column('had_night_pain', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('night_pain_level', sa.Integer(), nullable=True),
        sa.Column('disruptors', sa.Text(), nullable=True),        # JSON list
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('ai_insights', sa.Text(), nullable=True),
        sa.Column('sleep_date', sa.String(10), nullable=True),   # "YYYY-MM-DD"
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sleep_logs_id', 'sleep_logs', ['id'])

    # ── pain_video_analyses ──────────────────────────────────────────────────
    op.create_table(
        'pain_video_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('video_url', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('facial_pain_score', sa.Float(), nullable=True),
        sa.Column('voice_pain_indicators', sa.Text(), nullable=True),
        sa.Column('behavioral_indicators', sa.Text(), nullable=True),
        sa.Column('overall_pain_estimate', sa.Float(), nullable=True),
        sa.Column('ai_observations', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('pain_log_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pain_log_id'], ['pain_logs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pain_video_analyses_id', 'pain_video_analyses', ['id'])


def downgrade():
    op.drop_index('ix_pain_video_analyses_id', table_name='pain_video_analyses')
    op.drop_table('pain_video_analyses')
    op.drop_index('ix_sleep_logs_id', table_name='sleep_logs')
    op.drop_table('sleep_logs')
    op.drop_index('ix_water_logs_id', table_name='water_logs')
    op.drop_table('water_logs')
    op.drop_index('ix_food_logs_id', table_name='food_logs')
    op.drop_table('food_logs')
