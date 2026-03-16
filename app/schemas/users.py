"""Pydantic schemas for User resources."""

import uuid

from pydantic import BaseModel, EmailStr, field_validator

from app.models.users import UserRole


class UserBase(BaseModel):
    """Shared fields for user read/write operations."""

    email: EmailStr
    full_name: str
    role: UserRole


class UserCreate(UserBase):
    """Schema for creating a new user (includes plain-text password)."""

    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """Ensure the password meets the minimum length requirement."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserRead(UserBase):
    """Schema returned when reading user data from the API."""

    id: uuid.UUID
    model_config = {"from_attributes": True}
