"""RescheduleProposal ORM model."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.scheduling import ScheduleEvent


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RescheduleProposal(Base):
    """A teacher's request to move an existing session to a new time slot."""

    __tablename__ = "reschedule_proposals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedule_events.id"), nullable=False)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    new_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ProposalStatus.PENDING,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )

    event: Mapped["ScheduleEvent"] = relationship("ScheduleEvent", foreign_keys=[event_id])
    proposer: Mapped["User"] = relationship("User", foreign_keys=[proposed_by])
