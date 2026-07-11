"""Seed demo user with raw SQL + psycopg2 (no ORM).

Usage:
    cd backend/
    DATABASE_URL="postgresql://user:pass@host:5432/dbname" python scripts/seed_demo_raw.py
"""

import os
import sys
from urllib.parse import parse_qs, urlparse

import bcrypt
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("FATAL: DATABASE_URL required")

DEMO_EMAIL = "demo@veinly.eu"
DEMO_PASSWORD = "DemoPassword123!"
BCRYPT_ROUNDS = 12  # matches app's passlib bcrypt default


def _fix_url(url: str) -> str:
    """Convert asyncpg-style URL to psycopg2-compatible."""
    parsed = urlparse(url)
    if "+asyncpg" in parsed.scheme:
        scheme = parsed.scheme.replace("+asyncpg", "")
        url = url.replace(parsed.scheme, scheme)
    # Strip netloc from query params
    qs = parse_qs(parsed.query)
    sslmode = qs.pop("sslmode", None)
    if parsed.scheme.startswith("postgresql"):
        qs.pop("ssl", None)
    return url


def main():
    url = _fix_url(DATABASE_URL)
    print(f"Connecting to database...")

    conn = psycopg2.connect(url)
    conn.autocommit = False

    try:
        hashed = bcrypt.hashpw(
            DEMO_PASSWORD.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")

        cur = conn.cursor()

        # Check if user exists
        cur.execute("SELECT id FROM users WHERE email = %s", (DEMO_EMAIL,))
        existing = cur.fetchone()

        if existing:
            cur.execute(
                "UPDATE users SET hashed_password = %s WHERE email = %s",
                (hashed, DEMO_EMAIL),
            )
            print(f"Updated password for existing user: {DEMO_EMAIL}")
        else:
            cur.execute(
                """
                INSERT INTO users (name, email, hashed_password, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                """,
                ("Demo User", DEMO_EMAIL, hashed),
            )
            print(f"Created user: {DEMO_EMAIL}")

        conn.commit()
        print("Done.")
    except Exception as e:
        conn.rollback()
        sys.exit(f"FATAL: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
