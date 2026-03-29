from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from typing import List
from collections import Counter
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.pain_log import PainLog
from app.schemas.analytics import TrendsResponse, TrendDataPoint, AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/trends/", response_model=TrendsResponse)
def get_trends(
    granularity: str = Query("day", regex="^(day|week|month)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logs = (
        db.query(PainLog)
        .filter(PainLog.user_id == current_user.id)
        .order_by(PainLog.timestamp.asc())
        .all()
    )

    if not logs:
        return TrendsResponse(granularity=granularity, data=[])

    # Group by period
    buckets: dict = {}
    for log in logs:
        ts = log.timestamp
        if granularity == "day":
            key = ts.strftime("%Y-%m-%d")
        elif granularity == "week":
            # ISO week
            key = f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}"
        else:  # month
            key = ts.strftime("%Y-%m")

        if key not in buckets:
            buckets[key] = []
        buckets[key].append(log.pain_level)

    data = []
    for period, levels in sorted(buckets.items()):
        data.append(
            TrendDataPoint(
                period=period,
                average_pain=round(sum(levels) / len(levels), 2),
                entry_count=len(levels),
            )
        )

    return TrendsResponse(granularity=granularity, data=data)


@router.get("/summary/", response_model=AnalyticsSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logs = (
        db.query(PainLog)
        .filter(PainLog.user_id == current_user.id)
        .all()
    )

    if not logs:
        return AnalyticsSummary(total_entries=0)

    pain_levels = [l.pain_level for l in logs]
    avg_pain = round(sum(pain_levels) / len(pain_levels), 2)

    location_counter = Counter(l.pain_location for l in logs)
    most_common_location = location_counter.most_common(1)[0][0] if location_counter else None

    all_symptoms = []
    for log in logs:
        if log.symptoms:
            all_symptoms.extend(log.symptoms)
    symptom_counter = Counter(all_symptoms)
    most_common_symptoms = [s for s, _ in symptom_counter.most_common(5)]

    return AnalyticsSummary(
        total_entries=len(logs),
        average_pain=avg_pain,
        most_common_location=most_common_location,
        most_common_symptoms=most_common_symptoms,
        highest_pain_recorded=max(pain_levels),
        lowest_pain_recorded=min(pain_levels),
    )
