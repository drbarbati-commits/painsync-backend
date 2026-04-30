from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date


class PainLogCreate(BaseModel):
    pain_level: int = Field(..., ge=1, le=10)
    pain_location: str = Field(..., min_length=1, max_length=255)
    pain_locations: Optional[List[str]] = []
    duration_hours: Optional[float] = Field(None, ge=0)
    duration_minutes: Optional[float] = Field(None, ge=0)
    body_temp_celsius: Optional[float] = Field(None, ge=30.0, le=45.0)
    weight_at_log_kg: Optional[float] = Field(None, ge=0, le=500)
    symptoms: Optional[List[str]] = []
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None


class PainLogResponse(BaseModel):
    id: int
    user_id: int
    pain_level: int
    pain_location: str
    pain_locations: Optional[List[str]] = []
    duration_hours: Optional[float] = None
    duration_minutes: Optional[float] = None
    body_temp_celsius: Optional[float] = None
    weight_at_log_kg: Optional[float] = None
    symptoms: Optional[List[str]] = []
    notes: Optional[str] = None
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedPainLogs(BaseModel):
    items: List[PainLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Activity Log ─────────────────────────────────────────────────────────────

class ActivityLogCreate(BaseModel):
    date: Optional[date] = None
    steps: Optional[int] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    active_minutes: Optional[int] = Field(None, ge=0)
    calories_burned: Optional[float] = Field(None, ge=0)
    activity_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    source: Optional[str] = 'manual'


class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    date: date
    steps: Optional[int] = None
    distance_km: Optional[float] = None
    active_minutes: Optional[int] = None
    calories_burned: Optional[float] = None
    activity_type: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ActivitySummary(BaseModel):
    date: date
    total_steps: int
    total_distance_km: float
    total_active_minutes: int
    total_calories_burned: float
    entries: List[ActivityLogResponse]
