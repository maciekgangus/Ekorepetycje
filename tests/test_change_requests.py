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


async def test_responder_can_accept(client: AsyncClient, cr_env):
    """Responder accepts → event times updated, status=ACCEPTED."""
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    from app.models.scheduling import ScheduleEvent

    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    student_cookie = env["student_cookie"]

    # Teacher creates the request (student is responder)
    new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    assert r.status_code == 201
    cr_id = r.json()["id"]

    # Student (responder) accepts
    r2 = await client.patch(
        f"/api/change-requests/{cr_id}/accept",
        cookies={"session": student_cookie},
        headers={"X-CSRF-Token": _csrf(student_cookie)},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "accepted"

    # Verify event times were updated in DB
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        ev = await s.get(ScheduleEvent, env["event_id"])
        assert ev is not None
        assert ev.start_time.hour == (env["event_start"] + timedelta(hours=2)).hour
    await engine.dispose()


async def test_proposer_cannot_accept(client: AsyncClient, cr_env):
    """The proposer cannot accept their own request."""
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    cr_id = r.json()["id"]

    # Teacher (proposer) tries to accept — should be 403
    r2 = await client.patch(
        f"/api/change-requests/{cr_id}/accept",
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    assert r2.status_code == 403


async def test_accept_already_resolved_returns_409(client: AsyncClient, cr_env):
    """Accepting an already-accepted request returns 409."""
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    student_cookie = env["student_cookie"]
    new_start = (env["event_start"] + timedelta(hours=2)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=3)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    cr_id = r.json()["id"]
    await client.patch(
        f"/api/change-requests/{cr_id}/accept",
        cookies={"session": student_cookie},
        headers={"X-CSRF-Token": _csrf(student_cookie)},
    )
    # Accept again
    r3 = await client.patch(
        f"/api/change-requests/{cr_id}/accept",
        cookies={"session": student_cookie},
        headers={"X-CSRF-Token": _csrf(student_cookie)},
    )
    assert r3.status_code == 409


async def test_responder_can_reject(client: AsyncClient, cr_env):
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    student_cookie = env["student_cookie"]
    new_start = (env["event_start"] + timedelta(hours=4)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=5)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    cr_id = r.json()["id"]
    r2 = await client.patch(
        f"/api/change-requests/{cr_id}/reject",
        cookies={"session": student_cookie},
        headers={"X-CSRF-Token": _csrf(student_cookie)},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "rejected"


async def test_proposer_can_cancel(client: AsyncClient, cr_env):
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    new_start = (env["event_start"] + timedelta(hours=4)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=5)).isoformat()
    r = await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    cr_id = r.json()["id"]
    r2 = await client.patch(
        f"/api/change-requests/{cr_id}/cancel",
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


async def test_pending_count_for_teacher(client: AsyncClient, cr_env):
    """pending-count reflects PENDING requests where user is proposer or responder."""
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    student_cookie = env["student_cookie"]

    # Teacher proposes → student has 1 pending incoming
    new_start = (env["event_start"] + timedelta(hours=5)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=6)).isoformat()
    await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )

    r = await client.get(
        "/api/change-requests/pending-count",
        cookies={"session": student_cookie},
    )
    assert r.status_code == 200
    assert int(r.text) >= 1


async def test_list_change_requests(client: AsyncClient, cr_env):
    """GET /api/change-requests returns requests involving the current user."""
    env = cr_env
    teacher_cookie = env["teacher_cookie"]
    new_start = (env["event_start"] + timedelta(hours=5)).isoformat()
    new_end = (env["event_start"] + timedelta(hours=6)).isoformat()
    await client.post(
        "/api/change-requests",
        json={"event_id": str(env["event_id"]),
              "new_start": new_start, "new_end": new_end},
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": _csrf(teacher_cookie)},
    )

    r = await client.get(
        "/api/change-requests",
        cookies={"session": teacher_cookie},
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(item["event_id"] == str(env["event_id"]) for item in data)


async def test_admin_cannot_approve_reject_proposals(client: AsyncClient, admin_in_db):
    """Old admin approval endpoints are removed — must return 404 or 405."""
    admin_id, admin_cookie = admin_in_db
    fake_id = str(uuid.uuid4())

    r1 = await client.post(
        f"/admin/proposals/{fake_id}/approve",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": _csrf(admin_cookie)},
    )
    assert r1.status_code in (404, 405)

    r2 = await client.post(
        f"/admin/proposals/{fake_id}/reject",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": _csrf(admin_cookie)},
    )
    assert r2.status_code in (404, 405)


async def test_email_stubs_are_callable(cr_env):
    """Smoke test: email functions don't raise when RESEND_API_KEY is unset."""
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    from app.models.scheduling import ScheduleEvent, EventStatus
    from app.services.email import send_change_request_email, send_change_request_outcome_email
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    class FakeUser:
        id = uuid.uuid4()
        full_name = "Test User"
        email = "test@test.com"
        role = None

    class FakeEvent:
        id = uuid.uuid4()
        title = "Math lesson"
        start_time = now
        end_time = now
        teacher_id = uuid.uuid4()
        student_id = uuid.uuid4()

    class FakeCR:
        id = uuid.uuid4()
        event_id = uuid.uuid4()
        proposer_id = uuid.uuid4()
        responder_id = uuid.uuid4()
        new_start = now
        new_end = now
        note = "test"
        status = ChangeRequestStatus.PENDING
        created_at = now
        resolved_at = None
        proposer = FakeUser()
        responder = FakeUser()

    await send_change_request_email(FakeCR(), FakeEvent())
    await send_change_request_outcome_email(FakeCR(), FakeEvent(), accepted=True)
    await send_change_request_outcome_email(FakeCR(), FakeEvent(), accepted=False)
