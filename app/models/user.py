from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    medical_history = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)
    primary_condition = Column(String(255), nullable=True)
    pain_duration_years = Column(Float, nullable=True)
    pain_areas = Column(Text, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    language = Column(String(10), nullable=True, default='en')
    country = Column(String(100), nullable=True)
    unit_weight = Column(String(10), nullable=True, default='kg')
    unit_height = Column(String(10), nullable=True, default='cm')
    unit_temperature = Column(String(10), nullable=True, default='celsius')
    unit_volume = Column(String(10), nullable=True, default='ml')
    avatar_url = Column(String(2048), nullable=True)
    # Subscription / trial
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    subscription_status = Column(String(50), nullable=True, default='trial')
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    pain_logs = relationship("PainLog", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    triage_assessments = relationship("TriageAssessment", back_populates="user", cascade="all, delete-orphan")
    food_logs = relationship("FoodLog", back_populates="user", cascade="all, delete-orphan")
    water_logs = relationship("WaterLog", back_populates="user", cascade="all, delete-orphan")
    sleep_logs = relationship("SleepLog", back_populates="user", cascade="all, delete-orphan")
    video_analyses = relationship("PainVideoAnalysis", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="password_reset_tokens")
