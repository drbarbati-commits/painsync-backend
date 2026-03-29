from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum, Float, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base


class UrgencyLevel(str, enum.Enum):
    emergency = "emergency"
    urgent = "urgent"
    routine = "routine"


class TriageAssessment(Base):
    __tablename__ = "triage_assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pain_level = Column(Integer, nullable=False)
    pain_location = Column(String(255), nullable=False)
    duration_hours = Column(Float, nullable=True)
    symptoms = Column(ARRAY(String), nullable=True, default=[])
    notes = Column(Text, nullable=True)
    urgency = Column(Enum(UrgencyLevel), nullable=False)
    recommendation = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="triage_assessments")
