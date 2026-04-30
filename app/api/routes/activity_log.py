from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from typing import Optional

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.activity_log import ActivityLog
from app.schemas.pain_log import ActivityLogCreate, ActivityLogResponse, ActivitySummary

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.post("/", response_model=ActivityLogResponse, status_code=201)
def log_activity(
    payload: ActivityLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = ActivityLog(
        user_id=current_user.id,
        date=payload.date or date.today(),
        steps=payload.steps,
        distance_km=payload.distance_km,
        active_minutes=payload.active_minutes,
        calories_burned=payload.calories_burned,
        activity_type=payload.activity_type or 'walking',
        notes=payload.notes,
        source=payload.source or 'manual',
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/today", response_model=ActivitySummary)
def get_today_activity(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    entries = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id, ActivityLog.date == today)
        .order_by(ActivityLog.created_at.desc())
        .all()
    )
    return ActivitySummary(
        date=today,
        total_steps=sum(e.steps or 0 for e in entries),
        total_distance_km=sum(e.distance_km or 0 for e in entries),
        total_active_minutes=sum(e.active_minutes or 0 for e in entries),
        total_calories_burned=sum(e.calories_burned or 0 for e in entries),
        entries=entries,
    )


@router.get("/history", response_model=list[ActivityLogResponse])
def get_activity_history(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == current_user.id, ActivityLog.date >= cutoff)
        .order_by(ActivityLog.date.desc(), ActivityLog.created_at.desc())
        .all()
    )


@router.delete("/{entry_id}", status_code=204)
def delete_activity(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(ActivityLog).filter(
        ActivityLog.id == entry_id, ActivityLog.user_id == current_user.id
    ).first()
    if entry:
        db.delete(entry)
        db.commit()
