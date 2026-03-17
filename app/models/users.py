"""User ORM model."""

from __future__ import annotations

import uuid
import enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent


class UserRole(str, enum.Enum):
    """Roles available to platform users."""

    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    """Represents a platform user (admin, teacher, or student)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    offerings: Mapped[list["Offering"]] = relationship(
        "Offering", back_populates="teacher", foreign_keys="[Offering.teacher_id]"
    )
    taught_events: Mapped[list["ScheduleEvent"]] = relationship(
        "ScheduleEvent", back_populates="teacher", foreign_keys="[ScheduleEvent.teacher_id]"
    )
    enrolled_events: Mapped[list["ScheduleEvent"]] = relationship(
        "ScheduleEvent", back_populates="student", foreign_keys="[ScheduleEvent.student_id]"
    )
