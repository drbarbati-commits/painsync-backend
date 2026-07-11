#!/usr/bin/env python3
"""Create demo user via raw SQL + psycopg2 — no ORM imports.

Usage:
    cd backend/
    DATABASE_URL="postgresql://..." python scripts/create_demo_user_simple.py
"""

import os
import sys

import bcrypt
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("FATAL: DATABASE_URL environment variable required.")

DEMO_EMAIL = "demo@veinly.eu"
DEMO_PASSWORD = "DemoPassword123!"
BCRYPT_ROUNDS = 12  # matches app's passlib bcrypt default


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    try:
        hashed = bcrypt.hashpw(
            DEMO_PASSWORD.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users (name, email, hashed_password, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (email) DO UPDATE
                SET hashed_password = EXCLUDED.hashed_password
            """,
            ("Demo User", DEMO_EMAIL, hashed),
        )

        conn.commit()
        print(f"Demo user '{DEMO_EMAIL}' created/updated.")
    except Exception as e:
        conn.rollback()
        sys.exit(f"FATAL: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
