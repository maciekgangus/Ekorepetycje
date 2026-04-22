"""Pydantic schema for the landing page contact form."""

from pydantic import BaseModel, EmailStr, Field


class ContactForm(BaseModel):
    """Fields submitted via the public contact form."""

    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    subject: str = Field("", max_length=300)
    message: str = Field(..., min_length=1, max_length=5000)
