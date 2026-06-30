from __future__ import annotations

import math
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.deps import get_async_current_user
from app.models.user import User
from app.models.wellness import FoodLog
from app.schemas.wellness import FoodLogResponse, PaginatedFoodLogs
from app.services.food_service import analyze_food_image

router = APIRouter(prefix="/food-logs", tags=["Food Logs"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_SIZE_MB = 10


@router.post("/", response_model=FoodLogResponse, status_code=status.HTTP_201_CREATED)
async def create_food_log(
    file: UploadFile = File(...),
    meal_type: str = Form(None),
    notes: str = Form(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: jpeg, png, webp, gif.",
        )
    contents = await file.read()
    if len(contents) > _MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {_MAX_SIZE_MB} MB.",
        )

    result = analyze_food_image(
        image_data=contents,
        content_type=file.content_type,
        meal_type=meal_type,
        notes=notes,
    )

    log = FoodLog(
        user_id=current_user.id,
        meal_type=meal_type,
        food_description=result.get("food_description"),
        estimated_calories=result.get("estimated_calories"),
        estimated_protein_g=result.get("estimated_protein_g"),
        estimated_carbs_g=result.get("estimated_carbs_g"),
        estimated_fat_g=result.get("estimated_fat_g"),
        ai_notes=result.get("ai_notes"),
        notes=notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("/", response_model=PaginatedFoodLogs)
async def list_food_logs(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count(FoodLog.id)).where(FoodLog.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .order_by(FoodLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()

    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    return PaginatedFoodLogs(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
