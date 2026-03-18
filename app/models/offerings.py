"""Offering ORM model."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.scheduling import ScheduleEvent
    from app.models.series import RecurringSeries


class Offering(Base):
    """A tutoring offering created by a teacher."""

    __tablename__ = "offerings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    teacher: Mapped["User"] = relationship("User", back_populates="offerings", foreign_keys=[teacher_id])
    events: Mapped[list["ScheduleEvent"]] = relationship(
        "ScheduleEvent", back_populates="offering", foreign_keys="[ScheduleEvent.offering_id]"
    )
    series: Mapped[list["RecurringSeries"]] = relationship(
        "RecurringSeries", back_populates="offering"
    )
