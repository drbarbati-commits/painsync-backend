import json
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.models.wellness import FoodLog, WaterLog, SleepLog, PainVideoAnalysis
from app.schemas.wellness import (
    FoodLogCreate, FoodLogResponse, PaginatedFoodLogs,
    WaterLogCreate, WaterLogUpdate, WaterLogResponse, WaterDaySummary,
    PaginatedWaterLogs, WeeklyAlcoholSummary,
    SleepLogCreate, SleepLogResponse, SleepSummary,
    VideoAnalysisCreate, VideoAnalysisResponse,
    WellnessDashboard,
)
from app.services.claude_service import analyze_food_photos, analyze_pain_video_text

router = APIRouter(prefix="/wellness", tags=["Wellness"])

WEEKLY_ALCOHOL_LIMITS = {
    "United Kingdom": 14.0,
    "UK": 14.0,
    "GB": 14.0,
    "United States": 14.0,
    "US": 14.0,
    "Germany": 12.0,
    "DE": 12.0,
    "France": 14.0,
    "FR": 14.0,
    "Canada": 14.0,
    "CA": 14.0,
    "Australia": 14.0,
    "AU": 14.0,
    "Spain": 14.0,
    "Italy": 14.0,
    "Netherlands": 14.0,
    "Sweden": 9.0,
    "SE": 9.0,
    "Ireland": 14.0,
    "IE": 14.0,
}


def _normalize_country(raw: Optional[str]) -> str:
    if not raw:
        return "United Kingdom"
    value = raw.strip()
    aliases = {
        "UK": "United Kingdom",
        "GB": "United Kingdom",
        "US": "United States",
        "DE": "Germany",
        "FR": "France",
        "CA": "Canada",
        "AU": "Australia",
        "SE": "Sweden",
        "IE": "Ireland",
    }
    return aliases.get(value.upper(), value)


def _calculate_alcohol_units(amount_ml: float, abv: Optional[float]) -> float:
    if not abv or abv <= 0:
        return 0.0
    return (amount_ml * abv) / 1000.0


# ─── Wellness Dashboard ───────────────────────────────────────────────────────

@router.get("/dashboard/", response_model=WellnessDashboard)
def get_wellness_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    water_entries = db.query(WaterLog).filter(
        WaterLog.user_id == current_user.id,
        WaterLog.logged_at >= today_start,
        WaterLog.logged_at <= today_end,
    ).all()
    today_water = sum(w.amount_ml for w in water_entries)
    water_goal = 2000.0
    water_pct = min((today_water / water_goal) * 100, 100) if today_water > 0 else 0.0

    last_sleep = db.query(SleepLog).filter(
        SleepLog.user_id == current_user.id,
    ).order_by(SleepLog.created_at.desc()).first()

    today_meals = db.query(FoodLog).filter(
        FoodLog.user_id == current_user.id,
        FoodLog.logged_at >= today_start,
        FoodLog.logged_at <= today_end,
    ).all()
    today_calories = sum(f.estimated_calories or 0 for f in today_meals) or None

    week_ago = datetime.now() - timedelta(days=7)
    weekly_sleeps = db.query(SleepLog).filter(
        SleepLog.user_id == current_user.id,
        SleepLog.created_at >= week_ago,
    ).all()
    durations = [s.duration_hours for s in weekly_sleeps if s.duration_hours]
    qualities = [s.quality_rating for s in weekly_sleeps if s.quality_rating]
    weekly_avg_hours = sum(durations) / len(durations) if durations else None
    weekly_avg_quality = sum(qualities) / len(qualities) if qualities else None

    return WellnessDashboard(
        today_water_ml=today_water,
        today_water_goal_ml=water_goal,
        today_water_percentage=water_pct,
        last_sleep=last_sleep,
        today_meals=len(today_meals),
        today_calories=today_calories,
        weekly_avg_sleep_hours=weekly_avg_hours,
        weekly_avg_sleep_quality=weekly_avg_quality,
    )


# ─── Food Log ─────────────────────────────────────────────────────────────────

@router.post("/food/", response_model=FoodLogResponse, status_code=status.HTTP_201_CREATED)
def create_food_log(
    data: FoodLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = FoodLog(user_id=current_user.id, **data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/food/{food_log_id}/analyze/", response_model=FoodLogResponse)
def analyze_food_log(
    food_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(FoodLog).filter(
        FoodLog.id == food_log_id,
        FoodLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Food log not found")
    if not entry.before_photo_url:
        raise HTTPException(status_code=400, detail="No photo URL available for analysis")

    result = analyze_food_photos(
        before_url=entry.before_photo_url,
        after_url=entry.after_photo_url,
        meal_type=entry.meal_type,
    )
    entry.food_description = result.get("food_description")
    entry.estimated_calories = result.get("estimated_calories")
    entry.estimated_protein_g = result.get("estimated_protein_g")
    entry.estimated_carbs_g = result.get("estimated_carbs_g")
    entry.estimated_fat_g = result.get("estimated_fat_g")
    entry.intake_percentage = result.get("intake_percentage")
    entry.ai_notes = result.get("ai_notes")
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/food/", response_model=PaginatedFoodLogs)
def list_food_logs(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    total = db.query(FoodLog).filter(FoodLog.user_id == current_user.id).count()
    items = (
        db.query(FoodLog)
        .filter(FoodLog.user_id == current_user.id)
        .order_by(FoodLog.logged_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return PaginatedFoodLogs(
        items=items, total=total, page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.delete("/food/{food_log_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_food_log(
    food_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(FoodLog).filter(
        FoodLog.id == food_log_id, FoodLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Food log not found")
    db.delete(entry)
    db.commit()


# ─── Water Log ────────────────────────────────────────────────────────────────

@router.post("/water/", response_model=WaterLogResponse, status_code=status.HTTP_201_CREATED)
def log_water(
    data: WaterLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = data.model_dump(exclude_unset=True)
    liquid_type = payload.get("liquid_type", "water")
    drink_type = payload.get("drink_type") or liquid_type
    amount_ml = float(payload.get("amount_ml", 0))
    is_alcoholic = bool(payload.get("is_alcoholic", False))
    abv = payload.get("abv")
    alcohol_units = payload.get("alcohol_units")
    if alcohol_units is None:
        alcohol_units = _calculate_alcohol_units(amount_ml, abv if is_alcoholic else 0.0)

    entry = WaterLog(
        user_id=current_user.id,
        liquid_type=liquid_type,
        drink_type=drink_type,
        amount_ml=amount_ml,
        is_alcoholic=is_alcoholic,
        abv=abv if is_alcoholic else 0.0,
        alcohol_units=alcohol_units if is_alcoholic else 0.0,
        notes=payload.get("notes"),
        logged_at=payload.get("logged_at") or datetime.now(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/water/today/", response_model=WaterDaySummary)
def get_today_water(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    entries = (
        db.query(WaterLog)
        .filter(
            WaterLog.user_id == current_user.id,
            WaterLog.logged_at >= today_start,
            WaterLog.logged_at <= today_end,
        )
        .order_by(WaterLog.logged_at.desc())
        .all()
    )
    total = sum(e.amount_ml for e in entries)
    goal = 2000.0
    return WaterDaySummary(
        date=today.isoformat(),
        total_ml=total,
        entries=entries,
        goal_ml=goal,
        percentage_of_goal=min((total / goal) * 100, 100) if total > 0 else 0.0,
    )


@router.get("/water/", response_model=list[WaterLogResponse])
def list_water_logs(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)
    return (
        db.query(WaterLog)
        .filter(WaterLog.user_id == current_user.id, WaterLog.logged_at >= since)
        .order_by(WaterLog.logged_at.desc())
        .all()
    )


@router.get("/liquid-intake/", response_model=PaginatedWaterLogs)
def list_liquid_intake(
    page: int = 1,
    page_size: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(WaterLog).filter(WaterLog.user_id == current_user.id)

    if start_date is not None:
        query = query.filter(WaterLog.logged_at >= start_date)
    if end_date is not None:
        query = query.filter(WaterLog.logged_at <= end_date)

    total = query.count()
    offset = (page - 1) * page_size
    items = (
        query.order_by(WaterLog.logged_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return PaginatedWaterLogs(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/liquid-intake/weekly-summary", response_model=WeeklyAlcoholSummary)
def weekly_liquid_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now()
    week_start = datetime.combine((now - timedelta(days=now.weekday())).date(), datetime.min.time())
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    entries = (
        db.query(WaterLog)
        .filter(
            WaterLog.user_id == current_user.id,
            WaterLog.logged_at >= week_start,
            WaterLog.logged_at <= week_end,
            WaterLog.is_alcoholic == True,
        )
        .all()
    )
    weekly_units = sum((entry.alcohol_units or 0.0) for entry in entries)

    country = _normalize_country(current_user.country)
    limit = WEEKLY_ALCOHOL_LIMITS.get(country, 14.0)
    pct = (weekly_units / limit) * 100 if limit > 0 else 0.0

    return WeeklyAlcoholSummary(
        week_start=week_start.date().isoformat(),
        week_end=week_end.date().isoformat(),
        country=country,
        weekly_limit_units=limit,
        weekly_units=weekly_units,
        percentage_of_limit=min(pct, 999.0),
    )


@router.put("/liquid-intake/{entry_id}", response_model=WaterLogResponse)
def update_liquid_intake(
    entry_id: int,
    payload: WaterLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(WaterLog).filter(
        WaterLog.id == entry_id,
        WaterLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Liquid intake entry not found")

    data = payload.model_dump(exclude_unset=True)
    for field in [
        "liquid_type",
        "drink_type",
        "amount_ml",
        "is_alcoholic",
        "abv",
        "notes",
        "logged_at",
    ]:
        if field in data:
            setattr(entry, field, data[field])

    if "amount_ml" in data or "abv" in data or "is_alcoholic" in data:
        is_alcoholic = entry.is_alcoholic or False
        entry.alcohol_units = (
            _calculate_alcohol_units(entry.amount_ml, entry.abv) if is_alcoholic else 0.0
        )
    elif "alcohol_units" in data:
        entry.alcohol_units = data["alcohol_units"]

    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/liquid-intake/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_liquid_intake(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(WaterLog).filter(
        WaterLog.id == entry_id,
        WaterLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Liquid intake entry not found")
    db.delete(entry)
    db.commit()



@router.delete("/water/{water_log_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_water_log(
    water_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(WaterLog).filter(
        WaterLog.id == water_log_id, WaterLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Water log not found")
    db.delete(entry)
    db.commit()


# ─── Sleep Log ────────────────────────────────────────────────────────────────

@router.post("/sleep/", response_model=SleepLogResponse, status_code=status.HTTP_201_CREATED)
def log_sleep(
    data: SleepLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today_str = date.today().isoformat()
    entry = SleepLog(
        user_id=current_user.id,
        bedtime=data.bedtime,
        wake_time=data.wake_time,
        duration_hours=data.duration_hours,
        quality_rating=data.quality_rating,
        had_night_pain=data.had_night_pain,
        night_pain_level=data.night_pain_level,
        disruptors=json.dumps(data.disruptors) if data.disruptors else None,
        notes=data.notes,
        sleep_date=today_str,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # Deserialize disruptors for response
    entry_dict = {
        "id": entry.id,
        "user_id": entry.user_id,
        "bedtime": entry.bedtime,
        "wake_time": entry.wake_time,
        "duration_hours": entry.duration_hours,
        "quality_rating": entry.quality_rating,
        "had_night_pain": entry.had_night_pain,
        "night_pain_level": entry.night_pain_level,
        "disruptors": json.loads(entry.disruptors) if entry.disruptors else None,
        "notes": entry.notes,
        "ai_insights": entry.ai_insights,
        "sleep_date": entry.sleep_date,
        "created_at": entry.created_at,
    }
    return SleepLogResponse(**entry_dict)


@router.get("/sleep/", response_model=list[SleepLogResponse])
def list_sleep_logs(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)
    entries = (
        db.query(SleepLog)
        .filter(SleepLog.user_id == current_user.id, SleepLog.created_at >= since)
        .order_by(SleepLog.created_at.desc())
        .all()
    )
    result = []
    for e in entries:
        result.append(SleepLogResponse(
            id=e.id, user_id=e.user_id, bedtime=e.bedtime, wake_time=e.wake_time,
            duration_hours=e.duration_hours, quality_rating=e.quality_rating,
            had_night_pain=e.had_night_pain, night_pain_level=e.night_pain_level,
            disruptors=json.loads(e.disruptors) if e.disruptors else None,
            notes=e.notes, ai_insights=e.ai_insights, sleep_date=e.sleep_date,
            created_at=e.created_at,
        ))
    return result


@router.get("/sleep/summary/", response_model=SleepSummary)
def get_sleep_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now() - timedelta(days=days)
    entries = db.query(SleepLog).filter(
        SleepLog.user_id == current_user.id,
        SleepLog.created_at >= since,
    ).all()

    if not entries:
        return SleepSummary(total_entries=0)

    durations = [e.duration_hours for e in entries if e.duration_hours]
    qualities = [e.quality_rating for e in entries if e.quality_rating]
    night_pain_count = sum(1 for e in entries if e.had_night_pain)

    best = max(entries, key=lambda e: e.quality_rating or 0, default=None)
    worst = min(entries, key=lambda e: e.quality_rating or 6, default=None)

    return SleepSummary(
        average_duration_hours=sum(durations) / len(durations) if durations else None,
        average_quality_rating=sum(qualities) / len(qualities) if qualities else None,
        total_entries=len(entries),
        best_sleep_date=best.sleep_date if best else None,
        worst_sleep_date=worst.sleep_date if worst else None,
        night_pain_frequency=(night_pain_count / len(entries)) * 100 if entries else None,
    )


@router.delete("/sleep/{sleep_log_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_sleep_log(
    sleep_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(SleepLog).filter(
        SleepLog.id == sleep_log_id, SleepLog.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Sleep log not found")
    db.delete(entry)
    db.commit()


# ─── Video Pain Analysis ──────────────────────────────────────────────────────

@router.post("/video/", response_model=VideoAnalysisResponse, status_code=status.HTTP_201_CREATED)
def create_video_analysis(
    data: VideoAnalysisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = PainVideoAnalysis(user_id=current_user.id, **data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/video/{video_id}/analyze/", response_model=VideoAnalysisResponse)
def analyze_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(PainVideoAnalysis).filter(
        PainVideoAnalysis.id == video_id,
        PainVideoAnalysis.user_id == current_user.id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Video analysis not found")

    result = analyze_pain_video_text(
        video_url=entry.video_url,
        duration_seconds=entry.duration_seconds,
    )
    entry.facial_pain_score = result.get("facial_pain_score")
    entry.voice_pain_indicators = result.get("voice_pain_indicators")
    entry.behavioral_indicators = result.get("behavioral_indicators")
    entry.overall_pain_estimate = result.get("overall_pain_estimate")
    entry.ai_observations = result.get("ai_observations")
    entry.confidence_score = result.get("confidence_score")
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/video/", response_model=list[VideoAnalysisResponse])
def list_video_analyses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(PainVideoAnalysis)
        .filter(PainVideoAnalysis.user_id == current_user.id)
        .order_by(PainVideoAnalysis.created_at.desc())
        .all()
    )
