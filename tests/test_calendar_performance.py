"""Tests for date-windowed event fetching."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.auth import sign_session
from app.core.config import settings


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf(cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(settings.SECRET_KEY, salt="csrf").dumps(cookie)


@pytest.fixture
async def windowed_env():
    """Two events: one this week, one 6 weeks later. One teacher, one student."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_id = uuid.uuid4()
    student_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_near_id = uuid.uuid4()
    event_far_id = uuid.uuid4()

    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    near_start = now + timedelta(days=1)
    far_start  = now + timedelta(weeks=6)

    async with factory() as s:
        s.add(User(id=teacher_id, role=UserRole.TEACHER,
                   email=f"perf-t-{teacher_id}@test.com", hashed_password="h",
                   full_name="Perf Teacher"))
        s.add(User(id=student_id, role=UserRole.STUDENT,
                   email=f"perf-s-{student_id}@test.com", hashed_password="h",
                   full_name="Perf Student"))
        await s.flush()
        s.add(Offering(id=offering_id, title="Perf Subject",
                       base_price_per_hour=100, teacher_id=teacher_id))
        await s.flush()
        s.add(ScheduleEvent(id=event_near_id, title="Near Event",
                            start_time=near_start, end_time=near_start + timedelta(hours=1),
                            offering_id=offering_id, teacher_id=teacher_id,
                            student_id=student_id, status=EventStatus.SCHEDULED))
        s.add(ScheduleEvent(id=event_far_id, title="Far Event",
                            start_time=far_start, end_time=far_start + timedelta(hours=1),
                            offering_id=offering_id, teacher_id=teacher_id,
                            student_id=student_id, status=EventStatus.SCHEDULED))
        await s.commit()

    teacher_cookie = sign_session({"user_id": str(teacher_id)})

    yield {
        "teacher_id": teacher_id,
        "student_id": student_id,
        "offering_id": offering_id,
        "event_near_id": event_near_id,
        "event_far_id": event_far_id,
        "near_start": near_start,
        "far_start": far_start,
        "teacher_cookie": teacher_cookie,
    }

    async with factory() as s:
        from app.models.scheduling import ScheduleEvent as SE
        from app.models.offerings import Offering as Off
        from app.models.users import User as U
        for ev_id in (event_near_id, event_far_id):
            obj = await s.get(SE, ev_id)
            if obj: await s.delete(obj)
        await s.flush()
        off = await s.get(Off, offering_id)
        if off: await s.delete(off)
        await s.flush()
        for uid in (teacher_id, student_id):
            u = await s.get(U, uid)
            if u: await s.delete(u)
        await s.commit()
    await engine.dispose()


async def test_events_without_window_returns_all(client: AsyncClient, windowed_env):
    """No start/end params → all events returned (backwards-compatible)."""
    env = windowed_env
    r = await client.get(f"/api/events?teacher_id={env['teacher_id']}")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) in ids


async def test_events_with_window_excludes_far_event(client: AsyncClient, windowed_env):
    """start/end window filters out the far event."""
    env = windowed_env
    start = (env["near_start"] - timedelta(days=1)).isoformat()
    end   = (env["near_start"] + timedelta(days=14)).isoformat()
    r = await client.get(
        f"/api/events?teacher_id={env['teacher_id']}&start={start}&end={end}"
    )
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) not in ids


async def test_events_by_student_with_window(client: AsyncClient, windowed_env):
    """student_id + window also filters correctly."""
    env = windowed_env
    start = (env["near_start"] - timedelta(days=1)).isoformat()
    end   = (env["near_start"] + timedelta(days=14)).isoformat()
    r = await client.get(
        f"/api/events?student_id={env['student_id']}&start={start}&end={end}"
    )
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) not in ids
