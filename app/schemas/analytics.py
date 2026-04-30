from pydantic import BaseModel
from typing import List, Optional, Dict


class TrendDataPoint(BaseModel):
    period: str  # date string or week/month label
    average_pain: float
    entry_count: int


class TrendsResponse(BaseModel):
    granularity: str  # "day", "week", "month"
    data: List[TrendDataPoint]


class AnalyticsSummary(BaseModel):
    total_entries: int
    average_pain: Optional[float] = None
    most_common_location: Optional[str] = None
    most_common_symptoms: List[str] = []
    highest_pain_recorded: Optional[int] = None
    lowest_pain_recorded: Optional[int] = None


class LocationHeatmapResponse(BaseModel):
    granularity: str
    location_averages: Dict[str, float]  # location_name -> average_pain (0-10)
    total_logs: int
