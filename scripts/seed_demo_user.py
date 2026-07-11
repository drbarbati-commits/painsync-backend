"""Seed demo user account directly in database.

Usage:
    cd backend/
    python scripts/seed_demo_user.py

Requires DATABASE_URL env var.
"""

import os
import sys

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


def main():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        hashed = get_password_hash(DEMO_PASSWORD)

        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if user:
            user.hashed_password = hashed
            print(f"Updated existing user: {user.email}")
        else:
            user = User(
                name="Demo User",
                email=DEMO_EMAIL,
                hashed_password=hashed,
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
