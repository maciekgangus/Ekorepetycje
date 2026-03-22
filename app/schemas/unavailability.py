"""Pydantic schemas for RecurringUnavailSeries resources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.schemas.series import DaySlot  # reuse identical slot schema


class RecurringUnavailCreate(BaseModel):
    """Schema for creating a recurring unavailability series."""

    user_id: uuid.UUID
    note: str | None = Field(None, max_length=255)
    start_date: date
    interval_weeks: Annotated[int, Field(ge=1, le=52)]
    day_slots: Annotated[list[DaySlot], Field(min_length=1)]
    end_date: date | None = None
    end_count: Annotated[int | None, Field(ge=1, le=200)] = None

    @model_validator(mode="after")
    def validate_end_condition(self) -> "RecurringUnavailCreate":
        has_date = self.end_date is not None
        has_count = self.end_count is not None
        if has_date == has_count:
            raise ValueError("Provide exactly one of end_date or end_count.")
        if has_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class RecurringUnavailRead(BaseModel):
    """Schema returned when reading a recurring unavailability series."""

    id: uuid.UUID
    user_id: uuid.UUID
    note: str | None
    start_date: date
    interval_weeks: int
    day_slots: list[DaySlot]
    end_date: date | None
    end_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
