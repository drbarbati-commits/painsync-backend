from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    steps = Column(Integer, nullable=True)
    distance_km = Column(Float, nullable=True)
    active_minutes = Column(Integer, nullable=True)
    calories_burned = Column(Float, nullable=True)
    activity_type = Column(String(100), nullable=True)   # walking, running, cycling, other
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, default='manual')  # manual | healthkit | gps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="activity_logs")
