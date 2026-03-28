"""Integration tests for /api/offerings endpoints.

Note: POST /api/offerings has NO auth check in routes_api.py — it is intentionally
public for FullCalendar hydration. The admin-facing creation goes through /admin/offerings/create.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


# ── Fixture: teacher for offering FK ─────────────────────────────────────────

@pytest.fixture
async def teacher_for_offerings():
    """Seed a teacher row; yield teacher_id; cleanup offerings + teacher."""
    from app.models.users import User, UserRole
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    teacher_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"off-teacher-{teacher_id}@test.com",
            hashed_password="hashed",
            full_name="Offerings Teacher",
        ))
        await s.commit()

    yield teacher_id

    from sqlalchemy import select
    from app.models.offerings import Offering
    async with factory() as s:
        result = await s.execute(select(Offering).where(Offering.teacher_id == teacher_id))
        for o in result.scalars().all():
            await s.delete(o)
        await s.flush()
        t = await s.get(User, teacher_id)
        if t:
            await s.delete(t)
        await s.commit()
    await engine.dispose()


# ── GET /api/offerings ────────────────────────────────────────────────────────

async def test_get_offerings_returns_200(client):
    r = await client.get("/api/offerings")
    assert r.status_code == 200


async def test_get_offerings_returns_list(client):
    r = await client.get("/api/offerings")
    assert isinstance(r.json(), list)


# ── POST /api/offerings ───────────────────────────────────────────────────────

async def test_post_offerings_unauthenticated_creates_offering(client, teacher_for_offerings):
    """POST /api/offerings is an open JSON endpoint — no auth required."""
    teacher_id = teacher_for_offerings
    payload = {
        "title": "Fizyka",
        "description": "Lekcje fizyki",
        "base_price_per_hour": "120.00",
        "teacher_id": str(teacher_id),
    }
    r = await client.post("/api/offerings", json=payload)
    assert r.status_code == 201


async def test_post_offerings_creates_offering_with_correct_fields(client, teacher_for_offerings):
    teacher_id = teacher_for_offerings
    payload = {
        "title": "Chemia",
        "description": None,
        "base_price_per_hour": "80.00",
        "teacher_id": str(teacher_id),
    }
    r = await client.post("/api/offerings", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Chemia"
    assert data["teacher_id"] == str(teacher_id)
    assert "id" in data


async def test_post_offerings_returns_offering_read_schema(client, teacher_for_offerings):
    teacher_id = teacher_for_offerings
    payload = {
        "title": "Biologia",
        "base_price_per_hour": "95.50",
        "teacher_id": str(teacher_id),
    }
    r = await client.post("/api/offerings", json=payload)
    assert r.status_code == 201
    data = r.json()
    # OfferingRead must have these keys
    for key in ("id", "title", "base_price_per_hour", "teacher_id"):
        assert key in data
