from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class FoodLog(Base):
    """Tracks meal photo before/after eating with AI nutrition analysis."""
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    meal_type = Column(String(50), nullable=True)        # breakfast, lunch, dinner, snack
    before_photo_url = Column(Text, nullable=True)        # URL of photo before eating
    after_photo_url = Column(Text, nullable=True)         # URL of photo after eating
    food_description = Column(Text, nullable=True)        # AI-detected food items
    estimated_calories = Column(Float, nullable=True)
    estimated_protein_g = Column(Float, nullable=True)
    estimated_carbs_g = Column(Float, nullable=True)
    estimated_fat_g = Column(Float, nullable=True)
    intake_percentage = Column(Float, nullable=True)      # % of food consumed (before vs after)
    ai_notes = Column(Text, nullable=True)                # AI observations about eating ability
    pain_level_during = Column(Integer, nullable=True)    # pain level while eating (1-10)
    notes = Column(Text, nullable=True)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="food_logs")


class WaterLog(Base):
    """Tracks water and liquid intake."""
    __tablename__ = "water_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    liquid_type = Column(String(100), nullable=False, default="water")
    drink_type = Column(String(100), nullable=True)
    is_alcoholic = Column(Boolean, nullable=False, default=False)
    abv = Column(Float, nullable=True)
    alcohol_units = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    amount_ml = Column(Float, nullable=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="water_logs")


class SleepLog(Base):
    """Tracks sleep duration and quality — fields match Flutter SleepLogScreen."""
    __tablename__ = "sleep_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Flutter sends bedtime/wake_time as "HH:MM" strings
    bedtime = Column(String(5), nullable=True)            # e.g. "23:00"
    wake_time = Column(String(5), nullable=True)          # e.g. "07:00"
    duration_hours = Column(Float, nullable=True)
    quality_rating = Column(Integer, nullable=True)       # 1-5 star rating
    had_night_pain = Column(Boolean, nullable=True, default=False)
    night_pain_level = Column(Integer, nullable=True)     # 1-10 if had_night_pain
    disruptors = Column(Text, nullable=True)              # JSON list of disruptors
    notes = Column(Text, nullable=True)
    ai_insights = Column(Text, nullable=True)
    sleep_date = Column(String(10), nullable=True)        # ISO date "YYYY-MM-DD"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="sleep_logs")


class PainVideoAnalysis(Base):
    """Stores AI analysis of patient video clips for pain assessment."""
    __tablename__ = "pain_video_analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    video_url = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    facial_pain_score = Column(Float, nullable=True)      # 0-10 AI-estimated pain from face
    voice_pain_indicators = Column(Text, nullable=True)   # AI voice analysis results
    behavioral_indicators = Column(Text, nullable=True)   # AI movement/behavior analysis
    overall_pain_estimate = Column(Float, nullable=True)  # 0-10 combined estimate
    ai_observations = Column(Text, nullable=True)         # Full AI narrative
    confidence_score = Column(Float, nullable=True)       # 0-1 confidence
    pain_log_id = Column(Integer, ForeignKey("pain_logs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="video_analyses")
