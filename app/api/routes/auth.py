"""
auth.py — Authentication endpoints.

Supports:
  POST /auth/register           — Create account, return tokens
  POST /auth/login              — Authenticate, return tokens
  POST /auth/refresh            — Rotate refresh token, return new token pair
  POST /auth/logout             — Revoke tokens
  POST /auth/phone/send-otp     — Send 6-digit OTP via SMS (or log in dev)
  POST /auth/phone/verify-otp   — Verify OTP, return tokens
  GET  /auth/me                 — Return current user profile
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import string
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.deps import get_async_current_user
from app.core.config import settings
from app.core.security import (
    constant_time_compare,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.models.security import TokenBlacklist, OTPCode
from app.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserLogin,
    UserResponse,
    RefreshRequest,
    RefreshResponse,
    LogoutRequest,
    LogoutResponse,
    PhoneSendRequest,
    PhoneSendResponse,
    PhoneVerifyRequest,
    PhoneVerifyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ─── In-memory rate-limit state ────────────────────────────────────────────────
# { ip: [timestamp, ...] }
_refresh_rate_windows: dict[str, list[float]] = {}
_otp_send_windows: dict[str, list[float]] = {}
_otp_verify_windows: dict[str, list[float]] = {}

_WINDOW_SECONDS = 60
_MAX_REFRESH_PER_WINDOW = 5
_MAX_OTP_SEND_PER_WINDOW = 3
_MAX_OTP_VERIFY_PER_WINDOW = 5


def _check_rate_limit(
    windows: dict[str, list[float]],
    key: str,
    max_requests: int,
    window_seconds: int = _WINDOW_SECONDS,
) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    entries = windows.setdefault(key, [])
    entries[:] = [t for t in entries if t > cutoff]
    if len(entries) >= max_requests:
        retry_after = int(window_seconds - (now - entries[0])) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
        )
    entries.append(now)


# ─── Helpers ───────────────────────────────────────────────────────────────────


async def _create_token_pair(user_id: int) -> tuple[str, str]:
    """Create both access and refresh tokens for a user."""
    access = create_access_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh = create_refresh_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
    )
    return access, refresh


async def _blacklist_token(
    db: AsyncSession, token: str, token_type: str
) -> None:
    """Add a token to the blacklist if it has a valid JTI."""
    payload = decode_token(token)
    if payload is None:
        return
    jti = payload.get("jti")
    if not jti:
        return
    exp = payload.get("exp")
    if exp is None:
        return

    exists = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    )
    if exists.scalars().first() is not None:
        return

    db.add(
        TokenBlacklist(
            jti=jti,
            token_type=token_type,
            user_id=int(payload["sub"]) if payload.get("sub") else None,
            expires_at=datetime.utcfromtimestamp(exp),
        )
    )
    await db.commit()


def _phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()


# ─── POST /auth/register ───────────────────────────────────────────────────────


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserRegister,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        country=payload.country,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    access, refresh = await _create_token_pair(user.id)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ─── POST /auth/login ──────────────────────────────────────────────────────────


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(User).where(User.email == payload.email)
    )
    user = result.scalars().first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    access, refresh = await _create_token_pair(user.id)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ─── GET /auth/me ──────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_async_current_user),
):
    return current_user


# ─── POST /auth/refresh ────────────────────────────────────────────────────────


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    # Rate limit: max 5 refresh attempts per minute per IP
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _refresh_rate_windows, client_ip, _MAX_REFRESH_PER_WINDOW
    )

    # Decode and validate refresh token
    refresh_payload = decode_token(payload.refresh_token)
    if refresh_payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if refresh_payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token.",
        )

    jti = refresh_payload.get("jti")
    if jti:
        blacklisted = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        )
        if blacklisted.scalars().first() is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has already been used",
            )

    user_id = refresh_payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(User.id == int(user_id))
    )
    user = result.scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Blacklist old refresh token (token rotation)
    await _blacklist_token(db, payload.refresh_token, "refresh")

    # Issue new token pair
    new_access, new_refresh = await _create_token_pair(int(user_id))
    return RefreshResponse(
        access_token=new_access,
        refresh_token=new_refresh,
    )


# ─── POST /auth/logout ─────────────────────────────────────────────────────────


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    await _blacklist_token(db, payload.access_token, "access")
    if payload.refresh_token:
        await _blacklist_token(db, payload.refresh_token, "refresh")
    return LogoutResponse()


# ─── POST /auth/phone/send-otp ─────────────────────────────────────────────────


@router.post("/phone/send-otp", response_model=PhoneSendResponse)
async def send_otp(
    payload: PhoneSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _otp_send_windows, client_ip, _MAX_OTP_SEND_PER_WINDOW
    )

    phone = payload.phone.strip()
    ph = _phone_hash(phone)

    # Invalidate any existing unverified OTPs for this phone
    existing = await db.execute(
        select(OTPCode).where(
            OTPCode.phone_hash == ph,
            OTPCode.verified == False,  # noqa: E712
        )
    )
    for otp_row in existing.scalars().all():
        otp_row.verified = True  # Mark as consumed
    await db.commit()

    # Generate 6-digit OTP
    otp = "".join(random.choices(string.digits, k=6))
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires_at = time.time() + 300  # 5 minutes

    db.add(
        OTPCode(
            phone_hash=ph,
            otp_hash=otp_hash,
            expires_at=datetime.utcfromtimestamp(expires_at),
        )
    )
    await db.commit()

    # Try Twilio if configured, otherwise log to console
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
            logger.exception("Failed to send SMS via Twilio")

    if sms_sent:
        logger.info("OTP sent via SMS to %s", phone)
    else:
        logger.info(
            "OTP for %s: %s (SMS not configured, logging for dev)", phone, otp
        )

    return PhoneSendResponse(message="OTP sent successfully")


# ─── POST /auth/phone/verify (backward compat alias) ──────────────────────────


@router.post("/phone/verify", response_model=PhoneVerifyResponse)
async def verify_otp_legacy(
    payload: PhoneVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Legacy alias for /auth/phone/verify-otp."""
    return await verify_otp(payload, request, db)


# ─── POST /auth/phone/verify-otp ───────────────────────────────────────────────


@router.post("/phone/verify-otp", response_model=PhoneVerifyResponse)
async def verify_otp(
    payload: PhoneVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(
        _otp_verify_windows, client_ip, _MAX_OTP_VERIFY_PER_WINDOW
    )

    phone = payload.phone.strip()
    ph = _phone_hash(phone)

    now = datetime.utcnow()

    # Find the latest unverified OTP for this phone
    result = await db.execute(
        select(OTPCode).where(
            OTPCode.phone_hash == ph,
            OTPCode.verified == False,  # noqa: E712
            OTPCode.expires_at > now,
        ).order_by(OTPCode.id.desc()).limit(1)
    )
    otp_row = result.scalars().first()

    if otp_row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid OTP found. Please request a new code.",
        )

    # Increment attempt counter
    otp_row.attempts = (otp_row.attempts or 0) + 1
    await db.commit()

    if otp_row.attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please request a new code.",
        )

    # Constant-time comparison
    provided_hash = hashlib.sha256(payload.otp.encode()).hexdigest()
    if not constant_time_compare(provided_hash, otp_row.otp_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect OTP. Please try again.",
        )

    # Mark OTP as verified
    otp_row.verified = True
    await db.commit()

    # Find or create user by phone
    email = f"phone_{phone.replace('+', '')}@painsync.phone"
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        random_pw = "".join(
            random.choices(string.ascii_letters + string.digits, k=32)
        )
        user = User(
            name=f"User {phone[-4:]}",
            email=email,
            hashed_password=get_password_hash(random_pw),
            phone=phone,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if not user.phone:
            user.phone = phone
            await db.commit()

    access, refresh = await _create_token_pair(user.id)
    return PhoneVerifyResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )
