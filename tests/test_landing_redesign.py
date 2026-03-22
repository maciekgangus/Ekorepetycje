"""Tests for the landing page redesign routes."""
import pytest
from httpx import AsyncClient


def test_user_model_has_profile_fields():
    """User model must have photo_url, bio, specialties, created_at."""
    from app.models.users import User
    assert hasattr(User, "photo_url")
    assert hasattr(User, "bio")
    assert hasattr(User, "specialties")
    assert hasattr(User, "created_at")


async def test_landing_page_no_ampersand_in_subjects(client: AsyncClient):
    """Subject card headings must not contain & character."""
    r = await client.get("/")
    assert r.status_code == 200
    # Check subject names use 'i' not '&'
    assert "Matematyka i Fizyka" in r.text
    assert "Informatyka i IT" in r.text
    # Filter tabs should be gone
    assert 'hx-get="/subjects?level=' not in r.text


async def test_landing_hero_has_max_width_wrapper(client: AsyncClient):
    """Hero inner content must be wrapped in a max-width container."""
    r = await client.get("/")
    assert "max-w-7xl" in r.text


async def test_subject_detail_matematyka_returns_200(client: AsyncClient):
    r = await client.get("/przedmioty/matematyka")
    assert r.status_code == 200
    assert "Matematyka" in r.text


async def test_subject_detail_informatyka_returns_200(client: AsyncClient):
    r = await client.get("/przedmioty/informatyka")
    assert r.status_code == 200
    assert "Informatyka" in r.text


async def test_subject_detail_jezyki_returns_200(client: AsyncClient):
    r = await client.get("/przedmioty/jezyki-obce")
    assert r.status_code == 200
    assert "Języki" in r.text


async def test_subject_detail_unknown_slug_returns_404(client: AsyncClient):
    r = await client.get("/przedmioty/fizyka")
    assert r.status_code == 404


async def test_landing_page_teacher_section_hidden_when_no_teachers(client: AsyncClient):
    """Teacher section must be absent when no teachers have photo+bio.

    Relies on the test DB having no TEACHER rows with both photo_url and bio set.
    If this test becomes flaky, a write test preceding it has leaked data — see
    the isolation note in conftest.py.
    """
    r = await client.get("/")
    assert r.status_code == 200
    assert "Nasi Nauczyciele" not in r.text
