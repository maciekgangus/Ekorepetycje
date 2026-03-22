"""Pydantic schemas for RecurringSeries resources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, model_validator
from pydantic import Field


class DaySlot(BaseModel):
    """One time slot within a recurring week."""

    day: Annotated[int, Field(ge=0, le=6)]  # 0=Monday, 6=Sunday
    hour: Annotated[int, Field(ge=0, le=23)]
    minute: Annotated[int, Field(ge=0, le=59)]
    duration_minutes: Annotated[int, Field(ge=15, le=480)]


class RecurringSeriesCreate(BaseModel):
    """Schema for creating a new recurring series."""

    teacher_id: uuid.UUID
    student_id: uuid.UUID | None = None
    offering_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    start_date: date
    interval_weeks: Annotated[int, Field(ge=1, le=52)]
    day_slots: Annotated[list[DaySlot], Field(min_length=1)]
    end_date: date | None = None
    end_count: Annotated[int | None, Field(ge=1, le=200)] = None

    @model_validator(mode="after")
    def exactly_one_end_condition(self) -> "RecurringSeriesCreate":
        """Exactly one of end_date or end_count must be provided, and end_date must not precede start_date."""
        has_date = self.end_date is not None
        has_count = self.end_count is not None
        if has_date == has_count:  # both or neither
            raise ValueError("Provide exactly one of end_date or end_count.")
        if has_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class RecurringSeriesRead(BaseModel):
    """Schema returned when reading a recurring series."""

    id: uuid.UUID
    teacher_id: uuid.UUID
    student_id: uuid.UUID | None
    offering_id: uuid.UUID
    title: str
    start_date: date
    interval_weeks: int
    day_slots: list[DaySlot]
    end_date: date | None
    end_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
