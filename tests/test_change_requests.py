"""Bilateral reschedule proposal tests."""

def test_model_imports():
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    assert ChangeRequestStatus.PENDING == "pending"
    assert ChangeRequestStatus.ACCEPTED == "accepted"
    assert ChangeRequestStatus.REJECTED == "rejected"
    assert ChangeRequestStatus.CANCELLED == "cancelled"


def test_schema_imports():
    from app.schemas.change_requests import EventChangeRequestCreate, EventChangeRequestRead
    import uuid
    from datetime import datetime, timezone
    create = EventChangeRequestCreate(
        event_id=uuid.uuid4(),
        new_start=datetime.now(timezone.utc),
        new_end=datetime.now(timezone.utc),
        note="test",
    )
    assert create.note == "test"


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
async def cr_env():
    """Seed: teacher, student, offering, one SCHEDULED event."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_id = uuid.uuid4()
    student_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_id = uuid.uuid4()

    tomorrow = datetime.now(timezone.utc).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)

    async with factory() as s:
        s.add(User(id=teacher_id, role=UserRole.TEACHER,
                   email=f"cr-teacher-{teacher_id}@test.com",
                   hashed_password="h", full_name="CR Teacher"))
        s.add(User(id=student_id, role=UserRole.STUDENT,
                   email=f"cr-student-{student_id}@test.com",
                   hashed_password="h", full_name="CR Student"))
        await s.flush()
        s.add(Offering(id=offering_id, title="CR Subject",
                       base_price_per_hour=100, teacher_id=teacher_id))
        await s.flush()
        s.add(ScheduleEvent(
            id=event_id, title="CR Event",
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=1),
            offering_id=offering_id, teacher_id=teacher_id,
            student_id=student_id, status=EventStatus.SCHEDULED,
        ))
        await s.commit()

    teacher_cookie = sign_session({"user_id": str(teacher_id)})
    student_cookie = sign_session({"user_id": str(student_id)})

    yield {
        "teacher_id": teacher_id,
        "student_id": student_id,
        "offering_id": offering_id,
        "event_id": event_id,
        "event_start": tomorrow,
        "teacher_cookie": teacher_cookie,
        "student_cookie": student_cookie,
    }

    from app.models.change_requests import EventChangeRequest
    from sqlalchemy import select as sa_select
    async with factory() as s:
        crs = (await s.execute(
            sa_select(EventChangeRequest).where(EventChangeRequest.event_id == event_id)
        )).scalars().all()
        for cr in crs:
            await s.delete(cr)
        ev = await s.get(ScheduleEvent, event_id)
        if ev:
            await s.delete(ev)
        off = await s.get(Offering, offering_id)
        if off:
            await s.delete(off)
        await s.flush()
        for uid in (teacher_id, student_id):
            u = await s.get(User, uid)
            if u:
                await s.delete(u)
        await s.commit()
    await engine.dispose()


async def test_teacher_can_create_change_request(client: AsyncClient, cr_env):
    env = cr_env
    cookie = env["teacher_cookie"]
    new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={
            "event_id": str(env["event_id"]),
            "new_start": new_start,
            "new_end": new_end,
            "note": "Czy możemy przesunąć?",
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _csrf(cookie)},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["proposer_id"] == str(env["teacher_id"])
    assert data["responder_id"] == str(env["student_id"])
    assert data["status"] == "pending"


async def test_student_can_create_change_request(client: AsyncClient, cr_env):
    env = cr_env
    cookie = env["student_cookie"]
    new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={
            "event_id": str(env["event_id"]),
            "new_start": new_start,
            "new_end": new_end,
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _csrf(cookie)},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["proposer_id"] == str(env["student_id"])
    assert data["responder_id"] == str(env["teacher_id"])


async def test_unrelated_user_cannot_create_change_request(client: AsyncClient, cr_env):
    """A user who is neither teacher nor student of the event gets 403."""
    from app.models.users import User, UserRole

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    other_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=other_id, role=UserRole.STUDENT,
                   email=f"cr-other-{other_id}@test.com",
                   hashed_password="h", full_name="Other"))
        await s.commit()
    try:
        env = cr_env
        cookie = sign_session({"user_id": str(other_id)})
        new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
        new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
        r = await client.post(
            "/api/change-requests",
            json={"event_id": str(env["event_id"]),
                  "new_start": new_start, "new_end": new_end},
            cookies={"session": cookie},
            headers={"X-CSRF-Token": _csrf(cookie)},
        )
        assert r.status_code == 403
    finally:
        async with factory() as s:
            u = await s.get(User, other_id)
            if u:
                await s.delete(u)
            await s.commit()
        await engine.dispose()
