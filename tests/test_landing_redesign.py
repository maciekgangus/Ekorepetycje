"""Tests for the landing page redesign routes."""
import pytest
from httpx import AsyncClient, ASGITransport


async def test_user_model_has_profile_fields():
    """User model must have photo_url, bio, specialties, created_at."""
    from app.models.users import User
    assert hasattr(User, "photo_url")
    assert hasattr(User, "bio")
    assert hasattr(User, "specialties")
    assert hasattr(User, "created_at")
