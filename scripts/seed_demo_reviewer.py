"""Seed Apple App Store review demo account.

Usage:
    cd backend/
    python scripts/seed_demo_reviewer.py

Requires DATABASE_URL env var.
"""

import os
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.models.user import User

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("FATAL: DATABASE_URL environment variable is required.")

DEMO_EMAIL = "demo@veinly.eu"
DEMO_PASSWORD = "DemoPassword123!"


def _fix_asyncpg_ssl(url: str) -> str:
    """Strip sslmode for asyncpg — not needed for sync engine but harmless."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "sslmode" in query:
        sslmode = query.pop("sslmode")[0]
        if sslmode in ("require", "verify-ca", "verify-full"):
            query["ssl"] = ["require"]
    new_query = urlencode(query, doseq=True)
    return parsed._replace(query=new_query).geturl()


def main():
    url = _fix_asyncpg_ssl(DATABASE_URL)
    engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        hashed = get_password_hash(DEMO_PASSWORD)
        expires_at = datetime(2030, 1, 1, tzinfo=timezone.utc)

        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user:
            user.hashed_password = hashed
            user.subscription_status = "active"
            user.subscription_expires_at = expires_at
            print(f"Updated existing user: {user.email}")
        else:
            user = User(
                name="Apple Reviewer",
                email=DEMO_EMAIL,
                hashed_password=hashed,
                subscription_status="active",
                subscription_expires_at=expires_at,
                is_active=True,
            )
            db.add(user)
            print(f"Created user: {user.email}")

        db.commit()
        print("Done.")
    except Exception as e:
        db.rollback()
        sys.exit(f"FATAL: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
