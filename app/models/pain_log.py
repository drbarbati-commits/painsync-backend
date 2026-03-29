from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class PainLog(Base):
    __tablename__ = "pain_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pain_level = Column(Integer, nullable=False)  # 1-10
    pain_location = Column(String(255), nullable=False)
    duration_hours = Column(Float, nullable=True)
    symptoms = Column(ARRAY(String), nullable=True, default=[])
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="pain_logs")
