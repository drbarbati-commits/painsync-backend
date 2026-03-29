from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.triage import TriageAssessment, UrgencyLevel
from app.schemas.triage import TriageRequest, TriageResponse
from app.services.claude_service import triage_with_claude

router = APIRouter(prefix="/triage", tags=["Triage"])


@router.post("/", response_model=TriageResponse, status_code=status.HTTP_201_CREATED)
def create_triage(
    payload: TriageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pain_data = {
        "pain_level": payload.pain_level,
        "pain_location": payload.pain_location,
        "duration_hours": payload.duration_hours,
        "symptoms": payload.symptoms or [],
        "notes": payload.notes,
    }

    try:
        result = triage_with_claude(pain_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI triage service temporarily unavailable: {str(e)}",
        )

    urgency_str = result.get("urgency", "routine").lower()
    try:
        urgency = UrgencyLevel(urgency_str)
    except ValueError:
        urgency = UrgencyLevel.routine

    assessment = TriageAssessment(
        user_id=current_user.id,
        pain_level=payload.pain_level,
        pain_location=payload.pain_location,
        duration_hours=payload.duration_hours,
        symptoms=payload.symptoms or [],
        notes=payload.notes,
        urgency=urgency,
        recommendation=result.get("recommendation", ""),
        reasoning=result.get("reasoning", ""),
        model_used=result.get("model_used", ""),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/", response_model=List[TriageResponse])
def list_triage_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessments = (
        db.query(TriageAssessment)
        .filter(TriageAssessment.user_id == current_user.id)
        .order_by(TriageAssessment.created_at.desc())
        .limit(50)
        .all()
    )
    return assessments
