"""Pydantic schemas for ScheduleEvent resources."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.scheduling import EventStatus


class ScheduleEventBase(BaseModel):
    """Shared fields for schedule event read/write operations."""

    title: str
    start_time: datetime
    end_time: datetime
    offering_id: uuid.UUID
    teacher_id: uuid.UUID
    student_id: uuid.UUID | None = None
    status: EventStatus = EventStatus.SCHEDULED


class ScheduleEventCreate(ScheduleEventBase):
    """Schema for creating a new schedule event."""

    pass


class ScheduleEventRead(ScheduleEventBase):
    """Schema returned when reading schedule event data from the API."""

    id: uuid.UUID
    series_id: uuid.UUID | None = None
    model_config = {"from_attributes": True}
