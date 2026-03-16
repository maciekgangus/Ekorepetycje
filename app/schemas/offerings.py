"""Pydantic schemas for Offering resources."""

import uuid
from decimal import Decimal

from pydantic import BaseModel


class OfferingBase(BaseModel):
    """Shared fields for offering read/write operations."""

    title: str
    description: str | None = None
    base_price_per_hour: Decimal
    teacher_id: uuid.UUID


class OfferingCreate(OfferingBase):
    """Schema for creating a new offering."""

    pass


class OfferingRead(OfferingBase):
    """Schema returned when reading offering data from the API."""

    id: uuid.UUID
    model_config = {"from_attributes": True}
