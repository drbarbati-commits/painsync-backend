"""
social_auth.py — Social sign-in and phone OTP endpoints.

Supports:
  POST /auth/social/google   — Verify Google ID token, return PainSync JWT
  POST /auth/social/apple    — Verify Apple identity token, return PainSync JWT
  POST /auth/phone/send-otp  — Send (or simulate) a 6-digit OTP to a phone number
  POST /auth/phone/verify    — Verify OTP and return PainSync JWT
"""
import os
import random
import string
import hashlib
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

# ─── In-memory OTP store (use Redis in production) ────────────────────────────
# { phone_hash: (otp, expires_at) }
_otp_store: dict[str, tuple[str, float]] = {}
OTP_TTL_SECONDS = 300  # 5 minutes


# ─── Schemas ──────────────────────────────────────────────────────────────────

class GoogleTokenRequest(BaseModel):
    id_token: str
    name: Optional[str] = None

class AppleTokenRequest(BaseModel):
    identity_token: str
    name: Optional[str] = None

class PhoneSendRequest(BaseModel):
    phone: str  # E.164 format e.g. +491234567890

class PhoneVerifyRequest(BaseModel):
    phone: str
    otp: str


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
        # Generate a random secure password hash for social users
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

        # Apple identity token is a JWT — decode payload (middle segment)
        parts = payload.identity_token.split(".")
        if len(parts) != 3:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Apple identity token format",
            )
        # Add padding
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))

        email = claims.get("email")
        if not email:
            # Apple may hide the email — use sub as identifier
            sub = claims.get("sub", "")
            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Apple token does not contain an email or sub",
                )
            email = f"apple_{sub}@privaterelay.appleid.com"

        # Check expiry
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


# ─── Phone OTP ────────────────────────────────────────────────────────────────

def _phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()


@router.post("/phone/send-otp")
async def send_otp(payload: PhoneSendRequest):
    """
    Generate a 6-digit OTP for the given phone number.
    In production: send via Twilio/AWS SNS. Currently returns OTP in response for testing.
    """
    phone = payload.phone.strip()
    if not phone.startswith("+"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number must be in E.164 format (e.g. +491234567890)",
        )

    otp = "".join(random.choices(string.digits, k=6))
    key = _phone_hash(phone)
    _otp_store[key] = (otp, time.time() + OTP_TTL_SECONDS)

    # ── Try Twilio if configured ──────────────────────────────────────────────
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.getenv("TWILIO_PHONE_NUMBER", "")
    sms_sent = False
    if twilio_sid and twilio_token and twilio_from:
        try:
            import httpx
            auth = (twilio_sid, twilio_token)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json",
                    auth=auth,
                    data={
                        "From": twilio_from,
                        "To": phone,
                        "Body": f"Your PainSync verification code is: {otp}. Valid for 5 minutes.",
                    },
                )
            sms_sent = resp.status_code in (200, 201)
        except Exception:
            pass

    if sms_sent:
        return {"message": "OTP sent via SMS", "debug_otp": None}
    else:
        # Return OTP in response for development/testing (remove in production)
        return {
            "message": "OTP generated (SMS not configured — use debug_otp for testing)",
            "debug_otp": otp,
        }


@router.post("/phone/verify")
async def verify_otp(payload: PhoneVerifyRequest, db: Session = Depends(get_db)):
    """Verify the OTP and return a PainSync access token."""
    phone = payload.phone.strip()
    key = _phone_hash(phone)
    stored = _otp_store.get(key)

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found for this number. Please request a new code.",
        )

    otp, expires_at = stored
    if time.time() > expires_at:
        del _otp_store[key]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new code.",
        )

    if payload.otp != otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect OTP. Please try again.",
        )

    # OTP valid — clean up and find/create user
    del _otp_store[key]

    # Use phone number as the email identifier
    email = f"phone_{phone.replace('+', '')}@painsync.phone"
    user = _get_or_create_social_user(db, email, None, "phone")
    # Store phone number on user profile
    if not user.phone:
        user.phone = phone
        db.commit()

    return _issue_token(user)
