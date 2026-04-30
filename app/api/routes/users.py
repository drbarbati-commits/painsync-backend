from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Basic fields
    if payload.name is not None:
        current_user.name = payload.name
    if payload.age is not None:
        current_user.age = payload.age
    if payload.gender is not None:
        current_user.gender = payload.gender
    if payload.medical_history is not None:
        current_user.medical_history = payload.medical_history
    # Extended profile fields
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.weight_kg is not None:
        current_user.weight_kg = payload.weight_kg
    if payload.height_cm is not None:
        current_user.height_cm = payload.height_cm
    if payload.language is not None:
        current_user.language = payload.language
    if payload.country is not None:
        current_user.country = payload.country
    if payload.unit_weight is not None:
        current_user.unit_weight = payload.unit_weight
    if payload.unit_height is not None:
        current_user.unit_height = payload.unit_height
    if payload.unit_temperature is not None:
        current_user.unit_temperature = payload.unit_temperature
    if payload.unit_volume is not None:
        current_user.unit_volume = payload.unit_volume
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.delete(current_user)
    db.commit()
