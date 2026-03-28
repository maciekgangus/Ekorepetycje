"""Integration tests for /api/events endpoints."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.auth import sign_session
from app.core.config import settings
from app.main import app


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf_token_for(session_cookie: str) -> str:
    """Compute a valid CSRF token for a given signed session cookie value."""
    from itsdangerous import URLSafeSerializer
    signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")
    return signer.dumps(session_cookie)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _future_dt(offset_hours: int = 2) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=offset_hours)).isoformat()


async def _create_event_in_db(teacher_id: uuid.UUID, offering_id: uuid.UUID) -> uuid.UUID:
    """Directly insert a ScheduleEvent and return its id."""
    from app.models.scheduling import ScheduleEvent, EventStatus
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    event_id = uuid.uuid4()
    async with factory() as s:
        s.add(ScheduleEvent(
            id=event_id,
            title="Test Event",
            start_time=datetime.now(timezone.utc) + timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            offering_id=offering_id,
            teacher_id=teacher_id,
            status=EventStatus.SCHEDULED,
        ))
        await s.commit()
    await engine.dispose()
    return event_id


async def _delete_event_in_db(event_id: uuid.UUID) -> None:
    from app.models.scheduling import ScheduleEvent
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        ev = await s.get(ScheduleEvent, event_id)
        if ev:
            await s.delete(ev)
            await s.commit()
    await engine.dispose()


# ── Fixture: teacher + offering seeded together ───────────────────────────────

@pytest.fixture
async def teacher_with_offering():
    """Yield (teacher_id, offering_id, session_cookie). Cleans up after test."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    teacher_id = uuid.uuid4()
    offering_id = uuid.uuid4()

    async with factory() as s:
        s.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"t-{teacher_id}@test.com",
            hashed_password="hashed",
            full_name="Teacher",
        ))
        await s.flush()
        s.add(Offering(
            id=offering_id,
            title="Maths",
            base_price_per_hour=100,
            teacher_id=teacher_id,
        ))
        await s.commit()

    cookie = sign_session({"user_id": str(teacher_id)})
    yield teacher_id, offering_id, cookie

    async with factory() as s:
        from sqlalchemy import select
        from app.models.scheduling import ScheduleEvent
        result = await s.execute(
            select(ScheduleEvent).where(ScheduleEvent.teacher_id == teacher_id)
        )
        for ev in result.scalars().all():
            await s.delete(ev)
        await s.flush()
        o = await s.get(Offering, offering_id)
        if o:
            await s.delete(o)
        await s.flush()
        t = await s.get(User, teacher_id)
        if t:
            await s.delete(t)
        await s.commit()
    await engine.dispose()


# ── GET /api/events ───────────────────────────────────────────────────────────

async def test_get_events_unauthenticated_returns_list(client):
    """GET /api/events is public — should return 200 and a list."""
    r = await client.get("/api/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_get_events_filters_by_teacher_id(client, teacher_with_offering):
    teacher_id, offering_id, cookie = teacher_with_offering
    event_id = await _create_event_in_db(teacher_id, offering_id)
    try:
        r = await client.get(f"/api/events?teacher_id={teacher_id}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(e["id"] == str(event_id) for e in data)
        assert all(e["teacher_id"] == str(teacher_id) for e in data)
    finally:
        await _delete_event_in_db(event_id)


async def test_get_events_teacher_filter_excludes_others(client, teacher_with_offering):
    """Events belonging to a different teacher must not appear in the filter result."""
    teacher_id, offering_id, cookie = teacher_with_offering
    other_teacher_id = uuid.uuid4()
    r = await client.get(f"/api/events?teacher_id={other_teacher_id}")
    assert r.status_code == 200
    data = r.json()
    assert not any(e["teacher_id"] == str(teacher_id) for e in data)


# ── POST /api/events ──────────────────────────────────────────────────────────

async def test_post_event_unauthenticated_still_creates(client, teacher_with_offering):
    """POST /api/events has no auth guard — unauthenticated requests succeed (201)."""
    teacher_id, offering_id, _ = teacher_with_offering
    payload = {
        "title": "Unauth Event",
        "start_time": _future_dt(1),
        "end_time": _future_dt(2),
        "offering_id": str(offering_id),
        "teacher_id": str(teacher_id),
        "status": "scheduled",
    }
    r = await client.post("/api/events", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    # cleanup
    await _delete_event_in_db(uuid.UUID(data["id"]))


async def test_post_event_authenticated_as_teacher(client, teacher_with_offering):
    teacher_id, offering_id, cookie = teacher_with_offering
    payload = {
        "title": "Auth Event",
        "start_time": _future_dt(3),
        "end_time": _future_dt(4),
        "offering_id": str(offering_id),
        "teacher_id": str(teacher_id),
        "status": "scheduled",
    }
    r = await client.post(
        "/api/events",
        json=payload,
        cookies={"session": cookie},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Auth Event"
    assert data["teacher_id"] == str(teacher_id)
    # cleanup
    await _delete_event_in_db(uuid.UUID(data["id"]))


# ── PATCH /api/events/{id} ────────────────────────────────────────────────────

async def test_patch_event_unauthenticated_redirects(client, teacher_with_offering):
    """Unauthenticated PATCH hits require_teacher_or_admin → _LoginRedirect → 303."""
    teacher_id, offering_id, _ = teacher_with_offering
    event_id = await _create_event_in_db(teacher_id, offering_id)
    try:
        payload = {
            "title": "Changed",
            "start_time": _future_dt(1),
            "end_time": _future_dt(2),
            "offering_id": str(offering_id),
            "teacher_id": str(teacher_id),
            "status": "scheduled",
        }
        r = await client.patch(f"/api/events/{event_id}", json=payload)
        assert r.status_code in (303, 401, 403)
    finally:
        await _delete_event_in_db(event_id)


async def test_patch_event_as_owning_teacher(client, teacher_with_offering):
    """Teacher can PATCH their own event with valid CSRF."""
    teacher_id, offering_id, cookie = teacher_with_offering
    event_id = await _create_event_in_db(teacher_id, offering_id)
    try:
        csrf = _csrf_token_for(cookie)
        payload = {
            "title": "Updated Title",
            "start_time": _future_dt(1),
            "end_time": _future_dt(2),
            "offering_id": str(offering_id),
            "teacher_id": str(teacher_id),
            "status": "scheduled",
        }
        r = await client.patch(
            f"/api/events/{event_id}",
            json=payload,
            cookies={"session": cookie},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200
        assert r.json()["title"] == "Updated Title"
    finally:
        await _delete_event_in_db(event_id)


# ── DELETE /api/events/{id} ───────────────────────────────────────────────────

async def test_delete_event_unauthenticated_redirects(client, teacher_with_offering):
    """Unauthenticated DELETE → 303 redirect to /login."""
    teacher_id, offering_id, _ = teacher_with_offering
    event_id = await _create_event_in_db(teacher_id, offering_id)
    try:
        r = await client.delete(f"/api/events/{event_id}")
        assert r.status_code in (303, 401, 403)
    finally:
        await _delete_event_in_db(event_id)


async def test_delete_event_authenticated_as_teacher(client, teacher_with_offering):
    """Teacher can DELETE their own event with valid CSRF."""
    teacher_id, offering_id, cookie = teacher_with_offering
    event_id = await _create_event_in_db(teacher_id, offering_id)
    csrf = _csrf_token_for(cookie)
    r = await client.delete(
        f"/api/events/{event_id}",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 204


async def test_delete_nonexistent_event_returns_404(client, teacher_with_offering):
    _, _, cookie = teacher_with_offering
    csrf = _csrf_token_for(cookie)
    fake_id = uuid.uuid4()
    r = await client.delete(
        f"/api/events/{fake_id}",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404
