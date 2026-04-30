from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
import math

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.pain_log import PainLog
from app.schemas.pain_log import PainLogCreate, PainLogResponse, PaginatedPainLogs

router = APIRouter(prefix="/pain-log", tags=["Pain Log"])


@router.post("/", response_model=PainLogResponse, status_code=status.HTTP_201_CREATED)
def create_pain_log(
    payload: PainLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = PainLog(
        user_id=current_user.id,
        pain_level=payload.pain_level,
        pain_location=payload.pain_location,
        pain_locations=payload.pain_locations or [],
        duration_hours=payload.duration_hours,
        duration_minutes=payload.duration_minutes,
        body_temp_celsius=payload.body_temp_celsius,
        weight_at_log_kg=payload.weight_at_log_kg,
        symptoms=payload.symptoms or [],
        notes=payload.notes,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/", response_model=PaginatedPainLogs)
def list_pain_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(PainLog)
        .filter(PainLog.user_id == current_user.id)
        .order_by(PainLog.timestamp.desc())
    )
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedPainLogs(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{log_id}", response_model=PainLogResponse)
def get_pain_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = (
        db.query(PainLog)
        .filter(PainLog.id == log_id, PainLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pain log entry not found",
        )
    return log


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pain_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = (
        db.query(PainLog)
        .filter(PainLog.id == log_id, PainLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pain log entry not found",
        )
    db.delete(log)
    db.commit()
