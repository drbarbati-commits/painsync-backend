from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.deps import get_async_current_user
from app.models.user import User
from app.models.wellness import PainVideoAnalysis
from app.schemas.wellness import VideoAnalysisResponse
from app.services.video_service import analyze_pain_video

router = APIRouter(prefix="/pain-videos", tags=["Pain Videos"])

_ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/mpeg"}
_MAX_SIZE_MB = 100


@router.post("/", response_model=VideoAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def create_pain_video_analysis(
    file: UploadFile = File(...),
    duration_seconds: float = Form(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    if file.content_type not in _ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: mp4, mov, avi, webm, mpeg.",
        )
    contents = await file.read()
    if len(contents) > _MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {_MAX_SIZE_MB} MB.",
        )

    result = analyze_pain_video(
        video_data=contents,
        content_type=file.content_type,
        duration_seconds=duration_seconds,
    )

    analysis = PainVideoAnalysis(
        user_id=current_user.id,
        duration_seconds=duration_seconds,
        facial_pain_score=result.get("facial_pain_score"),
        voice_pain_indicators=result.get("voice_pain_indicators"),
        behavioral_indicators=result.get("behavioral_indicators"),
        overall_pain_estimate=result.get("overall_pain_estimate"),
        ai_observations=result.get("ai_observations"),
        confidence_score=result.get("confidence_score"),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


@router.get("/{video_id}", response_model=VideoAnalysisResponse)
async def get_pain_video_analysis(
    video_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_async_current_user),
):
    result = await db.execute(
        select(PainVideoAnalysis).where(
            PainVideoAnalysis.id == video_id,
            PainVideoAnalysis.user_id == current_user.id,
        )
    )
    analysis = result.scalars().first()
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video analysis not found.",
        )
    return analysis
