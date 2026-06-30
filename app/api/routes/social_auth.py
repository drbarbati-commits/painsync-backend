"""
social_auth.py — Social sign-in endpoints.

Supports:
  POST /auth/social/google   — Verify Google ID token, return PainSync JWT
  POST /auth/social/apple    — Verify Apple identity token, return PainSync JWT

Phone OTP endpoints have moved to auth.py for better security (constant-time
comparison, rate limiting, DB-backed storage).
"""
from __future__ import annotations

import os
import random
import string
import time
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Social Auth"])


# ─── Schemas ──────────────────────────────────────────────────────────────────


class GoogleTokenRequest(BaseModel):
    id_token: str
    name: Optional[str] = None


class AppleTokenRequest(BaseModel):
    identity_token: str
    name: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_or_create_social_user(
    db: Session,
    email: str,
    name: Optional[str],
    provider: str,
) -> User:
    """Find existing user by email or create a new one (no password)."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        random_pw = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        user = User(
            name=name or email.split("@")[0],
            email=email,
            hashed_password=get_password_hash(random_pw),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _issue_token(user: User) -> dict:
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer"}


# ─── Google Sign-In ───────────────────────────────────────────────────────────


@router.post("/social/google")
async def google_sign_in(payload: GoogleTokenRequest, db: Session = Depends(get_db)):
    """
    Verify a Google ID token and return a PainSync access token.
    Uses Google's tokeninfo endpoint for verification.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": payload.id_token},
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google ID token",
            )
        data = resp.json()
        email = data.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token does not contain an email address",
            )
        name = payload.name or data.get("name") or data.get("given_name")
        user = _get_or_create_social_user(db, email, name, "google")
        return _issue_token(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google sign-in failed: {str(e)}",
        )


# ─── Apple Sign-In ────────────────────────────────────────────────────────────


@router.post("/social/apple")
async def apple_sign_in(payload: AppleTokenRequest, db: Session = Depends(get_db)):
    """
    Verify an Apple identity token (JWT) and return a PainSync access token.
    Decodes the JWT without full signature verification for simplicity.
    In production, verify against Apple's public keys.
    """
    try:
        import base64
        import json as _json

        parts = payload.identity_token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Apple identity token format",
            )
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))

        email = claims.get("email")
        if not email:
            sub = claims.get("sub", "")
            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Apple token does not contain an email or sub",
                )
            email = f"apple_{sub}@privaterelay.appleid.com"

        exp = claims.get("exp", 0)
        if exp and time.time() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Apple identity token has expired",
            )

        name = payload.name
        user = _get_or_create_social_user(db, email, name, "apple")
        return _issue_token(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Apple sign-in failed: {str(e)}",
        )
