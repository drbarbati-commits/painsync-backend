from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    country: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None


class LogoutResponse(BaseModel):
    message: str = "Successfully logged out"


class PhoneSendRequest(BaseModel):
    phone: str = Field(
        ...,
        pattern=r"^\+[1-9]\d{6,14}$",
        description="Phone number in E.164 format (e.g. +491234567890)",
    )


class PhoneSendResponse(BaseModel):
    message: str


class PhoneVerifyRequest(BaseModel):
    phone: str = Field(
        ...,
        pattern=r"^\+[1-9]\d{6,14}$",
    )
    otp: str = Field(..., min_length=6, max_length=6)


class PhoneVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_history: Optional[str] = None
    medications: Optional[str] = None
    allergies: Optional[str] = None
    primary_condition: Optional[str] = None
    pain_duration_years: Optional[float] = None
    pain_areas: Optional[str] = None
    is_active: bool
    created_at: datetime
    phone: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    language: Optional[str] = None
    country: Optional[str] = None
    unit_weight: Optional[str] = None
    unit_height: Optional[str] = None
    unit_temperature: Optional[str] = None
    unit_volume: Optional[str] = None
    avatar_url: Optional[str] = None
    subscription_status: Optional[str] = None
    trial_started_at: Optional[datetime] = None
    subscription_expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    age: Optional[int] = Field(None, ge=0, le=150)
    gender: Optional[str] = Field(None, max_length=50)
    medical_history: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    height_cm: Optional[float] = Field(None, ge=0, le=300)
    language: Optional[str] = Field(None, max_length=10)
    country: Optional[str] = Field(None, max_length=100)
    unit_weight: Optional[str] = Field(None, max_length=10)
    unit_height: Optional[str] = Field(None, max_length=10)
    unit_temperature: Optional[str] = Field(None, max_length=20)
    unit_volume: Optional[str] = Field(None, max_length=10)
    avatar_url: Optional[str] = Field(None, max_length=2048)


class DeviceTokenRequest(BaseModel):
    token: str
    platform: str = Field(..., pattern=r"^(ios|android)$")


class MedicalProfileUpdate(BaseModel):
    medical_history: Optional[str] = None
    medications: Optional[str] = None
    allergies: Optional[str] = None
    primary_condition: Optional[str] = Field(None, max_length=255)
    pain_duration_years: Optional[float] = Field(None, ge=0)
    pain_areas: Optional[str] = None
