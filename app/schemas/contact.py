"""Pydantic schema for the landing page contact form."""

from pydantic import BaseModel, EmailStr


class ContactForm(BaseModel):
    """Fields submitted via the public contact form."""

    name: str
    email: EmailStr
    message: str
