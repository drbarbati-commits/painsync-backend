from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.triage import UrgencyLevel


class TriageRequest(BaseModel):
    pain_level: int = Field(..., ge=1, le=10)
    pain_location: str = Field(..., min_length=1, max_length=255)
    duration_hours: Optional[float] = Field(None, ge=0)
    symptoms: Optional[List[str]] = []
    notes: Optional[str] = None


class TriageResponse(BaseModel):
    id: int
    urgency: UrgencyLevel
    recommendation: str
    reasoning: str
    model_used: str
    created_at: datetime

    class Config:
        from_attributes = True
