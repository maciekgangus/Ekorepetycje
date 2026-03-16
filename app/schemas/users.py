"""Pydantic schemas for User resources."""

import uuid

from pydantic import BaseModel

from app.models.users import UserRole


class UserBase(BaseModel):
    """Shared fields for user read/write operations."""

    email: str
    full_name: str
    role: UserRole


class UserCreate(UserBase):
    """Schema for creating a new user (includes plain-text password)."""

    password: str


class UserRead(UserBase):
    """Schema returned when reading user data from the API."""

    id: uuid.UUID
    model_config = {"from_attributes": True}
