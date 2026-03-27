"""ScheduleEvent ORM model."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.series import RecurringSeries


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
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recurring_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=EventStatus.SCHEDULED,
        server_default=text("'scheduled'"),
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    offering: Mapped["Offering"] = relationship("Offering", back_populates="events")
    teacher: Mapped["User"] = relationship("User", back_populates="taught_events", foreign_keys=[teacher_id])
    student: Mapped["User | None"] = relationship("User", back_populates="enrolled_events", foreign_keys=[student_id])
    series: Mapped["RecurringSeries | None"] = relationship(
        "RecurringSeries", back_populates="events", foreign_keys=[series_id]
    )
