"""Tests for the landing page redesign routes."""
import pytest


def test_user_model_has_profile_fields():
    """User model must have photo_url, bio, specialties, created_at."""
    from app.models.users import User
    assert hasattr(User, "photo_url")
    assert hasattr(User, "bio")
    assert hasattr(User, "specialties")
    assert hasattr(User, "created_at")


@pytest.mark.anyio
async def test_landing_page_no_ampersand_in_subjects():
    """Subject card headings must not contain & character."""
    from app.main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    # Check subject names use 'i' not '&'
    assert "Matematyka i Fizyka" in r.text
    assert "Informatyka i IT" in r.text
    # Filter tabs should be gone
    assert 'hx-get="/subjects?level=' not in r.text


@pytest.mark.anyio
async def test_landing_hero_has_max_width_wrapper():
    """Hero inner content must be wrapped in a max-width container."""
    from app.main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "max-w-7xl" in r.text
