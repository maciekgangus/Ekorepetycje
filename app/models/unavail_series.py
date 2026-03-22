"""RecurringUnavailSeries ORM model — repeating busy-block rules for teachers and students."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.availability import UnavailableBlock


class RecurringUnavailSeries(Base):
    """A recurrence rule that pre-generates UnavailableBlock rows (same logic as RecurringSeries)."""

    __tablename__ = "recurring_unavail_series"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    day_slots: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "end_date IS NOT NULL OR end_count IS NOT NULL",
            name="ck_recurring_unavail_series_has_end_condition",
        ),
        CheckConstraint(
            "interval_weeks >= 1",
            name="ck_recurring_unavail_series_interval_weeks_positive",
        ),
    )

    user: Mapped["User"] = relationship("User", back_populates="unavail_series")
    blocks: Mapped[list["UnavailableBlock"]] = relationship(
        "UnavailableBlock",
        back_populates="series",
        order_by="UnavailableBlock.start_time",
    )
