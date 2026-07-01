"""Backfill schema objects that exist on prod (created out-of-band during
early development, before Alembic tracked every change) but were never
captured in a migration. Without this, `alembic upgrade head` against a
brand-new database leaves the app broken:

  - otp_codes / token_blacklist tables don't exist at all -> phone OTP
    login and logout/refresh-token-rotation 500 with UndefinedTable.
  - users.medications / allergies / primary_condition / pain_duration_years
    don't exist -> any query against the users table 500s with
    UndefinedColumnError (same failure mode fixed for pain_areas in 011).

All statements are idempotent (IF NOT EXISTS) since they must be a no-op
against the existing prod database.

Revision ID: 012_backfill_schema
Revises: 011_pain_areas
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = '012_backfill_schema'
down_revision = '011_pain_areas'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            phone_hash VARCHAR(64) NOT NULL,
            otp_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INTEGER,
            verified BOOLEAN,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_otp_codes_id ON otp_codes (id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_otp_codes_phone_hash ON otp_codes (phone_hash)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_blacklist (
            id SERIAL PRIMARY KEY,
            jti VARCHAR(255) NOT NULL,
            token_type VARCHAR(20) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_token_blacklist_id ON token_blacklist (id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_token_blacklist_jti ON token_blacklist (jti)"
    )

    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS medications TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS allergies TEXT")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_condition VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pain_duration_years FLOAT"
    )


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS pain_duration_years")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS primary_condition")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS allergies")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS medications")
    op.execute("DROP TABLE IF EXISTS token_blacklist")
    op.execute("DROP TABLE IF EXISTS otp_codes")
