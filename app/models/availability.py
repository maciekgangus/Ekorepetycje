"""UnavailableBlock ORM model — marks a user (teacher or student) as unavailable for a period."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.unavail_series import RecurringUnavailSeries


class UnavailableBlock(Base):
    """A period during which a teacher or student is unavailable."""

    __tablename__ = "unavailable_blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recurring_unavail_series.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="unavailable_blocks"
    )
    series: Mapped["RecurringUnavailSeries | None"] = relationship(
        "RecurringUnavailSeries", back_populates="blocks"
    )
