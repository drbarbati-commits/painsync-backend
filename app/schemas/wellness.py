from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Food Log ────────────────────────────────────────────────────────────────

class FoodLogCreate(BaseModel):
    meal_type: Optional[str] = None
    before_photo_url: Optional[str] = None
    after_photo_url: Optional[str] = None
    food_description: Optional[str] = None
    pain_level_during: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None


class FoodLogAnalyzeRequest(BaseModel):
    food_log_id: int
    before_photo_url: str
    after_photo_url: Optional[str] = None


class FoodLogResponse(BaseModel):
    id: int
    user_id: int
    meal_type: Optional[str]
    before_photo_url: Optional[str]
    after_photo_url: Optional[str]
    food_description: Optional[str]
    estimated_calories: Optional[float]
    estimated_protein_g: Optional[float]
    estimated_carbs_g: Optional[float]
    estimated_fat_g: Optional[float]
    intake_percentage: Optional[float]
    ai_notes: Optional[str]
    pain_level_during: Optional[int]
    notes: Optional[str]
    logged_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedFoodLogs(BaseModel):
    items: List[FoodLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Water Log ───────────────────────────────────────────────────────────────

class WaterLogCreate(BaseModel):
    liquid_type: str = "water"
    drink_type: Optional[str] = None
    amount_ml: float = Field(..., gt=0)
    is_alcoholic: bool = False
    abv: Optional[float] = Field(None, ge=0, le=100)
    alcohol_units: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    logged_at: Optional[datetime] = None


class WaterLogUpdate(BaseModel):
    liquid_type: Optional[str] = None
    drink_type: Optional[str] = None
    amount_ml: Optional[float] = Field(None, gt=0)
    is_alcoholic: Optional[bool] = None
    abv: Optional[float] = Field(None, ge=0, le=100)
    alcohol_units: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    logged_at: Optional[datetime] = None


class WaterLogResponse(BaseModel):
    id: int
    user_id: int
    liquid_type: str
    drink_type: Optional[str]
    amount_ml: float
    is_alcoholic: bool = False
    abv: Optional[float] = None
    alcohol_units: Optional[float] = None
    notes: Optional[str] = None
    logged_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class WaterDaySummary(BaseModel):
    date: str
    total_ml: float
    entries: List[WaterLogResponse]
    goal_ml: float = 2000.0
    percentage_of_goal: float


class PaginatedWaterLogs(BaseModel):
    items: List[WaterLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WeeklyAlcoholSummary(BaseModel):
    week_start: str
    week_end: str
    country: str
    weekly_limit_units: float
    weekly_units: float
    percentage_of_limit: float


# ─── Sleep Log ───────────────────────────────────────────────────────────────
# Field names match exactly what the Flutter SleepLogScreen sends

class SleepLogCreate(BaseModel):
    # Flutter sends bedtime/wake_time as "HH:MM" strings
    bedtime: Optional[str] = None          # e.g. "23:00"
    wake_time: Optional[str] = None        # e.g. "07:00"
    duration_hours: Optional[float] = None
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    had_night_pain: Optional[bool] = False
    night_pain_level: Optional[int] = Field(None, ge=1, le=10)
    disruptors: Optional[List[str]] = None
    notes: Optional[str] = None


class SleepLogResponse(BaseModel):
    id: int
    user_id: int
    bedtime: Optional[str]
    wake_time: Optional[str]
    duration_hours: Optional[float]
    quality_rating: Optional[int]
    had_night_pain: Optional[bool]
    night_pain_level: Optional[int]
    disruptors: Optional[List[str]]
    notes: Optional[str]
    ai_insights: Optional[str]
    sleep_date: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SleepSummary(BaseModel):
    average_duration_hours: Optional[float]
    average_quality_rating: Optional[float]
    total_entries: int
    best_sleep_date: Optional[str]
    worst_sleep_date: Optional[str]
    night_pain_frequency: Optional[float]


# ─── Pain Video Analysis ─────────────────────────────────────────────────────
# Flutter VideoAnalysisScreen sends: video_url, duration_seconds, pain_log_id

class VideoAnalysisCreate(BaseModel):
    video_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    pain_log_id: Optional[int] = None


class VideoAnalysisResponse(BaseModel):
    id: int
    user_id: int
    video_url: Optional[str]
    duration_seconds: Optional[float]
    facial_pain_score: Optional[float]
    voice_pain_indicators: Optional[str]
    behavioral_indicators: Optional[str]
    overall_pain_estimate: Optional[float]
    ai_observations: Optional[str]
    confidence_score: Optional[float]
    pain_log_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Wellness Dashboard Summary ──────────────────────────────────────────────

class WellnessDashboard(BaseModel):
    today_water_ml: float
    today_water_goal_ml: float = 2000.0
    today_water_percentage: float
    last_sleep: Optional[SleepLogResponse]
    today_meals: int
    today_calories: Optional[float]
    weekly_avg_sleep_hours: Optional[float]
    weekly_avg_sleep_quality: Optional[float]
