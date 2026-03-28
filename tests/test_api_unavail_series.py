"""Integration tests for /api/unavailability-series endpoints."""

import uuid
from datetime import date, datetime, timezone, timedelta

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
    """Seed a teacher; yield (teacher_id, cookie); cleanup unavail blocks/series + teacher."""
    from app.models.users import User, UserRole
    from app.models.availability import UnavailableBlock
    from app.models.unavail_series import RecurringUnavailSeries
    from sqlalchemy import select
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    teacher_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"unavail-t-{teacher_id}@test.com",
            hashed_password="hashed",
            full_name="Unavail Teacher",
        ))
        await s.commit()

    cookie = sign_session({"user_id": str(teacher_id)})
    yield teacher_id, cookie

    async with factory() as s:
        # blocks first (FK child)
        blk_result = await s.execute(
            select(UnavailableBlock).where(UnavailableBlock.user_id == teacher_id)
        )
        for b in blk_result.scalars().all():
            await s.delete(b)
        await s.flush()
        # series
        ser_result = await s.execute(
            select(RecurringUnavailSeries).where(RecurringUnavailSeries.user_id == teacher_id)
        )
        for sr in ser_result.scalars().all():
            await s.delete(sr)
        await s.flush()
        t = await s.get(User, teacher_id)
        if t:
            await s.delete(t)
        await s.commit()
    await engine.dispose()


def _series_payload(teacher_id: uuid.UUID) -> dict:
    return {
        "user_id": str(teacher_id),
        "note": "Wakacje",
        "start_date": "2026-07-07",
        "interval_weeks": 1,
        "day_slots": [{"day": 0, "hour": 10, "minute": 0, "duration_minutes": 60}],
        "end_count": 3,
    }


# ── POST /api/unavailability-series ──────────────────────────────────────────

async def test_post_unavail_series_unauthenticated_redirects(client, teacher_and_cookie):
    teacher_id, _ = teacher_and_cookie
    r = await client.post("/api/unavailability-series", json=_series_payload(teacher_id))
    assert r.status_code in (303, 401, 403)


async def test_post_unavail_series_authenticated_creates_series(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)
    r = await client.post(
        "/api/unavailability-series",
        json=_series_payload(teacher_id),
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201
    data = r.json()
    assert "series_id" in data
    assert data["blocks_created"] == 3


async def test_post_unavail_series_returns_block_count(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)
    payload = {
        "user_id": str(teacher_id),
        "note": None,
        "start_date": "2026-08-03",
        "interval_weeks": 1,
        "day_slots": [
            {"day": 0, "hour": 8, "minute": 0, "duration_minutes": 60},
            {"day": 2, "hour": 8, "minute": 0, "duration_minutes": 60},
        ],
        "end_count": 4,
    }
    r = await client.post(
        "/api/unavailability-series",
        json=payload,
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201
    assert r.json()["blocks_created"] == 4


# ── GET /api/unavailability-series/{id} ──────────────────────────────────────

async def test_get_unavail_series_authenticated_returns_data(client, teacher_and_cookie):
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)

    # Create first
    create_r = await client.post(
        "/api/unavailability-series",
        json=_series_payload(teacher_id),
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_r.status_code == 201
    series_id = create_r.json()["series_id"]

    # Fetch
    get_r = await client.get(
        f"/api/unavailability-series/{series_id}",
        cookies={"session": cookie},
    )
    assert get_r.status_code == 200
    data = get_r.json()
    assert data["id"] == series_id
    assert data["user_id"] == str(teacher_id)
    assert data["interval_weeks"] == 1
    assert len(data["day_slots"]) == 1


async def test_get_unavail_series_unauthenticated_redirects(client, teacher_and_cookie):
    """Unauthenticated GET hits require_teacher_or_admin → redirect."""
    r = await client.get(f"/api/unavailability-series/{uuid.uuid4()}")
    assert r.status_code in (303, 401, 403)


async def test_get_unavail_series_not_found_returns_404(client, teacher_and_cookie):
    _, cookie = teacher_and_cookie
    r = await client.get(
        f"/api/unavailability-series/{uuid.uuid4()}",
        cookies={"session": cookie},
    )
    assert r.status_code == 404


# ── DELETE /api/unavailability-series/{series_id}/from/{block_id} ────────────

async def test_delete_unavail_series_from_block_authenticated(client, teacher_and_cookie):
    """Create 3-block series, delete from block 2 → only block 1 remains; series survives."""
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)

    create_r = await client.post(
        "/api/unavailability-series",
        json=_series_payload(teacher_id),
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_r.status_code == 201
    series_id = create_r.json()["series_id"]

    # Retrieve the series to find block ids
    from app.models.availability import UnavailableBlock
    from sqlalchemy import select
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(UnavailableBlock)
            .where(UnavailableBlock.series_id == uuid.UUID(series_id))
            .order_by(UnavailableBlock.start_time)
        )
        blocks = res.scalars().all()
    await engine.dispose()

    assert len(blocks) == 3
    # Delete from the 2nd block onward
    second_block_id = str(blocks[1].id)

    del_r = await client.delete(
        f"/api/unavailability-series/{series_id}/from/{second_block_id}",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert del_r.status_code == 204

    # Verify only 1 block remains
    engine2 = _engine()
    factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with factory2() as s:
        res2 = await s.execute(
            select(UnavailableBlock)
            .where(UnavailableBlock.series_id == uuid.UUID(series_id))
        )
        remaining = res2.scalars().all()
    await engine2.dispose()
    assert len(remaining) == 1


async def test_delete_unavail_series_all_blocks_removes_series(client, teacher_and_cookie):
    """Deleting from the 1st block removes all blocks and the series itself."""
    teacher_id, cookie = teacher_and_cookie
    csrf = _csrf_token_for(cookie)

    create_r = await client.post(
        "/api/unavailability-series",
        json={
            "user_id": str(teacher_id),
            "note": None,
            "start_date": "2026-09-07",
            "interval_weeks": 1,
            "day_slots": [{"day": 0, "hour": 10, "minute": 0, "duration_minutes": 60}],
            "end_count": 2,
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert create_r.status_code == 201
    series_id = create_r.json()["series_id"]

    from app.models.availability import UnavailableBlock
    from app.models.unavail_series import RecurringUnavailSeries
    from sqlalchemy import select
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(UnavailableBlock)
            .where(UnavailableBlock.series_id == uuid.UUID(series_id))
            .order_by(UnavailableBlock.start_time)
        )
        blocks = res.scalars().all()
    await engine.dispose()

    first_block_id = str(blocks[0].id)
    del_r = await client.delete(
        f"/api/unavailability-series/{series_id}/from/{first_block_id}",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert del_r.status_code == 204

    # Series should be gone
    engine3 = _engine()
    factory3 = async_sessionmaker(engine3, class_=AsyncSession, expire_on_commit=False)
    async with factory3() as s:
        series = await s.get(RecurringUnavailSeries, uuid.UUID(series_id))
    await engine3.dispose()
    assert series is None
