"""Pydantic schemas for EventChangeRequest."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.change_requests import ChangeRequestStatus


class EventChangeRequestCreate(BaseModel):
    """Payload for creating a new change request. Backend derives responder_id."""

    event_id: uuid.UUID
    new_start: datetime
    new_end: datetime
    note: str | None = None


class EventChangeRequestRead(BaseModel):
    """Full representation returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    proposer_id: uuid.UUID
    responder_id: uuid.UUID
    new_start: datetime
    new_end: datetime
    note: str | None
    status: ChangeRequestStatus
    created_at: datetime
    resolved_at: datetime | None
