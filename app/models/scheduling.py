"""ScheduleEvent ORM model."""

import uuid
import enum
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class EventStatus(str, enum.Enum):
    """Lifecycle states for a scheduled tutoring session."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ScheduleEvent(Base):
    """A single tutoring session booked between a teacher and a student."""

    __tablename__ = "schedule_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    offering_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offerings.id"), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus), nullable=False,
        default=EventStatus.SCHEDULED,
        server_default=EventStatus.SCHEDULED.value
    )

    offering: Mapped["Offering"] = relationship("Offering")
    teacher: Mapped["User"] = relationship("User", back_populates="taught_events", foreign_keys=[teacher_id])
    student: Mapped["User | None"] = relationship("User", back_populates="enrolled_events", foreign_keys=[student_id])
