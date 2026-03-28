"""Integration tests for /api/availability endpoints."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.auth import sign_session
from app.core.config import settings


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf_token_for(session_cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")
    return signer.dumps(session_cookie)


# ── Fixture: teacher with cookie ──────────────────────────────────────────────

@pytest.fixture
async def teacher_and_cookie():
    """Seed a teacher; yield (teacher_id, cookie); cleanup blocks + teacher."""
    from app.models.users import User, UserRole
    from app.models.availability import UnavailableBlock
    from sqlalchemy import select
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    teacher_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"avail-teacher-{teacher_id}@test.com",
            hashed_password="hashed",
            full_name="Avail Teacher",
        ))
        await s.commit()

    cookie = sign_session({"user_id": str(teacher_id)})
    yield teacher_id, cookie

    async with factory() as s:
        result = await s.execute(
            select(UnavailableBlock).where(UnavailableBlock.user_id == teacher_id)
        )
        for b in result.scalars().all():
            await s.delete(b)
        await s.flush()
        t = await s.get(User, teacher_id)
        if t:
            await s.delete(t)
        await s.commit()
    await engine.dispose()


# ── GET /api/availability/{user_id} ──────────────────────────────────────────

async def test_get_availability_returns_200_for_known_user(client, teacher_and_cookie):
    teacher_id, _ = teacher_and_cookie
    r = await client.get(f"/api/availability/{teacher_id}")
    assert r.status_code == 200


async def test_get_availability_returns_list(client, teacher_and_cookie):
    teacher_id, _ = teacher_and_cookie
    r = await client.get(f"/api/availability/{teacher_id}")
    assert isinstance(r.json(), list)


async def test_get_availability_returns_200_for_unknown_user(client):
    """Unknown user_id → 200 with empty list (no auth required)."""
    r = await client.get(f"/api/availability/{uuid.uuid4()}")
    assert r.status_code == 200
    assert r.json() == []


# ── POST /api/availability ────────────────────────────────────────────────────

async def test_post_availability_unauthenticated_redirects(client, teacher_and_cookie):
    """No session cookie → require_teacher_or_admin fires _LoginRedirect → 303."""
    teacher_id, _ = teacher_and_cookie
    now = datetime.now(timezone.utc)
    data = {
        "user_id": str(teacher_id),
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(),
        "note": "",
    }
    r = await client.post("/api/availability", data=data)
    assert r.status_code in (303, 401, 403)


async def test_post_availability_authenticated_creates_block(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)
    now = datetime.now(timezone.utc)
    data = {
        "user_id": str(teacher_id),
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(),
        "note": "Test block",
    }
    r = await client.post(
        "/api/availability",
        data=data,
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201
    resp = r.json()
    assert "id" in resp


async def test_post_availability_returns_block_id(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)
    now = datetime.now(timezone.utc)
    data = {
        "user_id": str(teacher_id),
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "note": "",
    }
    r = await client.post(
        "/api/availability",
        data=data,
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201
    block_id = r.json()["id"]
    # The returned id should be a valid UUID string
    uuid.UUID(block_id)  # raises ValueError if not valid


# ── DELETE /api/availability — no dedicated endpoint (blocks deleted via series) ──
# The API has no standalone DELETE /api/availability/{id}; deletion goes through
# /api/unavailability-series/{series_id}/from/{block_id}. We test that the
# create-and-list round-trip is consistent.

async def test_created_block_appears_in_get(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)
    start = datetime.now(timezone.utc) + timedelta(days=10)
    end = start + timedelta(hours=1)
    data = {
        "user_id": str(teacher_id),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "note": "Visible block",
    }
    post_r = await client.post(
        "/api/availability",
        data=data,
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert post_r.status_code == 201
    block_id = post_r.json()["id"]

    get_r = await client.get(f"/api/availability/{teacher_id}")
    assert get_r.status_code == 200
    ids = [b["id"] for b in get_r.json()]
    assert block_id in ids
