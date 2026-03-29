"""EventChangeRequest ORM model."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.scheduling import ScheduleEvent


class ChangeRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class EventChangeRequest(Base):
    """A bilateral request to reschedule an event — either party may initiate."""

    __tablename__ = "event_change_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_events.id", ondelete="CASCADE"), nullable=False
    )
    proposer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    responder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    new_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ChangeRequestStatus] = mapped_column(
        SAEnum(ChangeRequestStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ChangeRequestStatus.PENDING,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    proposer: Mapped["User"] = relationship("User", foreign_keys=[proposer_id])
    responder: Mapped["User"] = relationship("User", foreign_keys=[responder_id])
    event: Mapped["ScheduleEvent"] = relationship(
        "ScheduleEvent", foreign_keys=[event_id]
    )
