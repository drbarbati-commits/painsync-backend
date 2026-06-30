from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.core.database import Base


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(255), unique=True, index=True, nullable=False)
    token_type = Column(String(20), nullable=False)  # "access" | "refresh"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = Column(DateTime(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone_hash = Column(String(64), index=True, nullable=False)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(), nullable=False)
    attempts = Column(Integer, default=0)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
