"""Authorization boundary tests.

Tests that roles cannot access resources or perform actions they are not
permitted to. Complements the happy-path tests in test_routes_*.py.
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select

from app.core.auth import sign_session
from app.core.config import settings


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf_token_for(session_cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")
    return signer.dumps(session_cookie)


# ── Fixture: two teachers + one event belonging to teacher_a ─────────────────

@pytest.fixture
async def two_teachers_one_event():
    """Seed two teachers and one offering+event owned by teacher_a.
    Yield dict. Cleanup on teardown.
    """
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_a_id = uuid.uuid4()
    teacher_b_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(
            id=teacher_a_id,
            role=UserRole.TEACHER,
            email=f"auth-ta-{teacher_a_id}@test.com",
            hashed_password="hashed",
            full_name="Teacher A",
        ))
        s.add(User(
            id=teacher_b_id,
            role=UserRole.TEACHER,
            email=f"auth-tb-{teacher_b_id}@test.com",
            hashed_password="hashed",
            full_name="Teacher B",
        ))
        await s.flush()
        s.add(Offering(
            id=offering_id,
            title="Subject",
            base_price_per_hour=100,
            teacher_id=teacher_a_id,
        ))
        await s.flush()
        s.add(ScheduleEvent(
            id=event_id,
            title="Teacher A Event",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            offering_id=offering_id,
            teacher_id=teacher_a_id,
            status=EventStatus.SCHEDULED,
        ))
        await s.commit()

    cookie_a = sign_session({"user_id": str(teacher_a_id)})
    cookie_b = sign_session({"user_id": str(teacher_b_id)})

    yield {
        "teacher_a_id": teacher_a_id,
        "teacher_b_id": teacher_b_id,
        "offering_id": offering_id,
        "event_id": event_id,
        "cookie_a": cookie_a,
        "cookie_b": cookie_b,
    }

    async with factory() as s:
        ev = await s.get(ScheduleEvent, event_id)
        if ev:
            await s.delete(ev)
        await s.flush()
        off = await s.get(Offering, offering_id)
        if off:
            await s.delete(off)
        await s.flush()
        for tid in (teacher_a_id, teacher_b_id):
            u = await s.get(User, tid)
            if u:
                await s.delete(u)
        await s.commit()
    await engine.dispose()


# ── Teacher cannot DELETE another teacher's event ─────────────────────────────

async def test_teacher_cannot_delete_other_teachers_event(client, two_teachers_one_event):
    env = two_teachers_one_event
    cookie_b = env["cookie_b"]
    csrf_b = _csrf_token_for(cookie_b)

    r = await client.delete(
        f"/api/events/{env['event_id']}",
        cookies={"session": cookie_b},
        headers={"X-CSRF-Token": csrf_b},
    )
    # Should get 403 — "Not your event"
    assert r.status_code == 403


async def test_teacher_cannot_patch_other_teachers_event(client, two_teachers_one_event):
    env = two_teachers_one_event
    cookie_b = env["cookie_b"]
    csrf_b = _csrf_token_for(cookie_b)

    payload = {
        "title": "Hijacked",
        "start_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "offering_id": str(env["offering_id"]),
        "teacher_id": str(env["teacher_a_id"]),
        "status": "scheduled",
    }
    r = await client.patch(
        f"/api/events/{env['event_id']}",
        json=payload,
        cookies={"session": cookie_b},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert r.status_code == 403


# ── Student cannot access /teacher/ routes ────────────────────────────────────

async def test_student_cannot_access_teacher_dashboard(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/teacher/", cookies={"session": cookie})
    assert r.status_code == 303
    location = r.headers["location"]
    # Redirected to student's own dashboard
    assert "/student/" in location


async def test_student_cannot_access_teacher_calendar(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/teacher/calendar", cookies={"session": cookie})
    assert r.status_code == 303


async def test_student_cannot_post_to_teacher_proposals(client, student_in_db):
    _, cookie = student_in_db
    r = await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(uuid.uuid4()),
            "new_start": datetime.now(timezone.utc).isoformat(),
            "new_end": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
        cookies={"session": cookie},
    )
    assert r.status_code == 303


# ── Teacher cannot access /admin/ routes ──────────────────────────────────────

async def test_teacher_cannot_access_admin_dashboard(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/admin/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/teacher/" in r.headers["location"]


async def test_teacher_cannot_access_admin_users(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/admin/users", cookies={"session": cookie})
    assert r.status_code == 303


async def test_teacher_cannot_access_admin_proposals(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/admin/proposals", cookies={"session": cookie})
    assert r.status_code == 303


# ── Admin CAN access /teacher/ (require_teacher_or_admin allows admins) ───────

async def test_admin_can_access_teacher_dashboard(client, admin_in_db):
    """Admin satisfies require_teacher_or_admin → 200 (not a 303)."""
    _, cookie = admin_in_db
    r = await client.get("/teacher/", cookies={"session": cookie})
    assert r.status_code == 200


# ── Admin can delete any teacher's event ─────────────────────────────────────

async def test_admin_can_delete_any_event(client, two_teachers_one_event, admin_in_db):
    env = two_teachers_one_event
    _, admin_cookie = admin_in_db
    admin_csrf = _csrf_token_for(admin_cookie)

    r = await client.delete(
        f"/api/events/{env['event_id']}",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 204
