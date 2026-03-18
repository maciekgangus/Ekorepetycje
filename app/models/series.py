"""RecurringSeries ORM model — stores recurrence rules for tutoring series."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent


class RecurringSeries(Base):
    """Recurrence rule for a set of tutoring sessions.

    Generates individual ScheduleEvent rows on creation.
    Stores the rule so 'edit from here' can re-generate forward events.
    """

    __tablename__ = "recurring_series"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    offering_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offerings.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # day_slots: list of {day: 0-6, hour: 0-23, minute: 0-59, duration_minutes: int}
    day_slots: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    teacher: Mapped["User"] = relationship("User", foreign_keys=[teacher_id])
    student: Mapped["User | None"] = relationship("User", foreign_keys=[student_id])
    offering: Mapped["Offering"] = relationship("Offering")
    events: Mapped[list["ScheduleEvent"]] = relationship(
        "ScheduleEvent", back_populates="series", order_by="ScheduleEvent.start_time"
    )
