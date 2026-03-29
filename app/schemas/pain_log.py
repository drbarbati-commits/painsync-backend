from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class PainLogCreate(BaseModel):
    pain_level: int = Field(..., ge=1, le=10)
    pain_location: str = Field(..., min_length=1, max_length=255)
    duration_hours: Optional[float] = Field(None, ge=0)
    symptoms: Optional[List[str]] = []
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None  # defaults to now() on server if not provided


class PainLogResponse(BaseModel):
    id: int
    user_id: int
    pain_level: int
    pain_location: str
    duration_hours: Optional[float] = None
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
