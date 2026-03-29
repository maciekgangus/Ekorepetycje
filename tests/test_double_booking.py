"""Double-booking prevention tests.

Verifies that POST /api/series returns 409 when the teacher or student
already has a SCHEDULED event overlapping one of the proposed slots.
"""

import uuid
from datetime import datetime, timezone, timedelta, date

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
async def booking_env():
    """Seed: one admin, one teacher, one student, one offering, one existing event."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    admin_id = uuid.uuid4()
    teacher_id = uuid.uuid4()
    student_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_id = uuid.uuid4()

    # Existing event: tomorrow 10:00–11:00 UTC
    tomorrow = datetime.now(timezone.utc).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    event_start = tomorrow
    event_end = tomorrow + timedelta(hours=1)

    async with factory() as s:
        s.add(User(id=admin_id, role=UserRole.ADMIN,
                   email=f"dbl-admin-{admin_id}@test.com",
                   hashed_password="h", full_name="Admin"))
        s.add(User(id=teacher_id, role=UserRole.TEACHER,
                   email=f"dbl-teacher-{teacher_id}@test.com",
                   hashed_password="h", full_name="Teacher DB"))
        s.add(User(id=student_id, role=UserRole.STUDENT,
                   email=f"dbl-student-{student_id}@test.com",
                   hashed_password="h", full_name="Student DB"))
        await s.flush()
        s.add(Offering(id=offering_id, title="Test Subject",
                       base_price_per_hour=100, teacher_id=teacher_id))
        await s.flush()
        s.add(ScheduleEvent(
            id=event_id, title="Existing event",
            start_time=event_start, end_time=event_end,
            offering_id=offering_id, teacher_id=teacher_id,
            student_id=student_id, status=EventStatus.SCHEDULED,
        ))
        await s.commit()

    admin_cookie = sign_session({"user_id": str(admin_id)})
    teacher_cookie = sign_session({"user_id": str(teacher_id)})

    yield {
        "admin_id": admin_id,
        "teacher_id": teacher_id,
        "student_id": student_id,
        "offering_id": offering_id,
        "event_id": event_id,
        "event_start": event_start,
        "admin_cookie": admin_cookie,
        "teacher_cookie": teacher_cookie,
    }

    async with factory() as s:
        for model, pk in [
            (ScheduleEvent, event_id),
            (Offering, offering_id),
        ]:
            obj = await s.get(model, pk)
            if obj:
                await s.delete(obj)
        await s.flush()
        for uid in (admin_id, teacher_id, student_id):
            u = await s.get(User, uid)
            if u:
                await s.delete(u)
        await s.commit()
    await engine.dispose()


def _overlapping_payload(env: dict) -> dict:
    """Series that generates one event overlapping the existing event."""
    start = env["event_start"]
    # start_date = tomorrow's date; slot at the same hour/minute as existing event
    start_date = start.date()
    day_of_week = (start.weekday())  # 0=Mon…6=Sun
    return {
        "teacher_id": str(env["teacher_id"]),
        "student_id": str(env["student_id"]),
        "offering_id": str(env["offering_id"]),
        "title": "Overlapping series",
        "start_date": start_date.isoformat(),
        "interval_weeks": 1,
        "day_slots": [{"day": day_of_week, "hour": start.hour,
                       "minute": start.minute, "duration_minutes": 60}],
        "end_count": 1,
    }


def _non_overlapping_payload(env: dict) -> dict:
    """Series that generates one event NOT overlapping the existing event."""
    start = env["event_start"]
    start_date = start.date()
    day_of_week = start.weekday()
    # 3 hours later — no overlap
    shifted_hour = (start.hour + 3) % 24
    return {
        "teacher_id": str(env["teacher_id"]),
        "student_id": str(env["student_id"]),
        "offering_id": str(env["offering_id"]),
        "title": "Non-overlapping series",
        "start_date": start_date.isoformat(),
        "interval_weeks": 1,
        "day_slots": [{"day": day_of_week, "hour": shifted_hour,
                       "minute": start.minute, "duration_minutes": 60}],
        "end_count": 1,
    }


async def test_create_series_rejects_teacher_double_booking(client: AsyncClient, booking_env):
    env = booking_env
    cookie = env["admin_cookie"]
    r = await client.post(
        "/api/series",
        json=_overlapping_payload(env),
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _csrf(cookie)},
    )
    assert r.status_code == 409
    assert "Nauczyciel" in r.json()["detail"]


async def test_create_series_rejects_student_double_booking(client: AsyncClient, booking_env):
    """Even if we use a different teacher, the student is already booked."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    env = booking_env
    other_teacher_id = uuid.uuid4()
    other_offering_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(id=other_teacher_id, role=UserRole.TEACHER,
                   email=f"dbl-ot-{other_teacher_id}@test.com",
                   hashed_password="h", full_name="Other Teacher"))
        await s.flush()
        s.add(Offering(id=other_offering_id, title="Other Subject",
                       base_price_per_hour=80, teacher_id=other_teacher_id))
        await s.commit()

    try:
        admin_cookie = env["admin_cookie"]
        start = env["event_start"]
        payload = {
            "teacher_id": str(other_teacher_id),
            "student_id": str(env["student_id"]),
            "offering_id": str(other_offering_id),
            "title": "Student conflict",
            "start_date": start.date().isoformat(),
            "interval_weeks": 1,
            "day_slots": [{"day": start.weekday(), "hour": start.hour,
                           "minute": start.minute, "duration_minutes": 60}],
            "end_count": 1,
        }
        r = await client.post(
            "/api/series",
            json=payload,
            cookies={"session": admin_cookie},
            headers={"X-CSRF-Token": _csrf(admin_cookie)},
        )
        assert r.status_code == 409
        assert "Uczeń" in r.json()["detail"]
    finally:
        async with factory() as s:
            off = await s.get(Offering, other_offering_id)
            if off:
                await s.delete(off)
            await s.flush()
            u = await s.get(User, other_teacher_id)
            if u:
                await s.delete(u)
            await s.commit()
        await engine.dispose()


async def test_create_series_allows_non_overlapping(client: AsyncClient, booking_env):
    env = booking_env
    cookie = env["admin_cookie"]
    r = await client.post(
        "/api/series",
        json=_non_overlapping_payload(env),
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _csrf(cookie)},
    )
    # Should succeed (201) and we clean up
    assert r.status_code == 201
    data = r.json()

    # Cleanup: delete the newly created series events
    if "series_id" in data:
        from app.models.series import RecurringSeries
        from app.models.scheduling import ScheduleEvent
        from sqlalchemy import select as sa_select

        engine = _engine()
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        series_id = uuid.UUID(data["series_id"])
        async with factory() as s:
            evs = (await s.execute(
                sa_select(ScheduleEvent).where(ScheduleEvent.series_id == series_id)
            )).scalars().all()
            for ev in evs:
                await s.delete(ev)
            await s.flush()
            sr = await s.get(RecurringSeries, series_id)
            if sr:
                await s.delete(sr)
            await s.commit()
        await engine.dispose()
