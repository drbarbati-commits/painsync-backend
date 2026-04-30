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
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_history: Optional[str] = None
    is_active: bool
    created_at: datetime
    # Extended profile fields
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
    # Subscription
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
    # Extended profile fields
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
