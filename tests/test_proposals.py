"""Integration tests for the reschedule proposal workflow.

Covers:
- Unauthenticated POST → redirect
- Teacher creates proposal → verify it exists as PENDING
- Admin approves proposal → status becomes APPROVED, event times updated
- Admin rejects proposal → status becomes REJECTED
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select

from app.core.auth import sign_session
from app.core.config import settings
from app.models.proposals import ProposalStatus


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf_token_for(session_cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")
    return signer.dumps(session_cookie)


# ── Fixture: full proposal environment ───────────────────────────────────────

@pytest.fixture
async def proposal_env():
    """Seed teacher, admin, offering, event.
    Yield dict with ids and cookies. Cleanup on teardown.
    """
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus
    from app.models.proposals import RescheduleProposal

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_id = uuid.uuid4()

    event_start = datetime.now(timezone.utc) + timedelta(days=3)
    event_end = event_start + timedelta(hours=1)

    async with factory() as s:
        s.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"prop-teacher-{teacher_id}@test.com",
            hashed_password="hashed",
            full_name="Proposal Teacher",
        ))
        s.add(User(
            id=admin_id,
            role=UserRole.ADMIN,
            email=f"prop-admin-{admin_id}@test.com",
            hashed_password="hashed",
            full_name="Proposal Admin",
        ))
        await s.flush()
        s.add(Offering(
            id=offering_id,
            title="Test Subject",
            base_price_per_hour=100,
            teacher_id=teacher_id,
        ))
        await s.flush()
        s.add(ScheduleEvent(
            id=event_id,
            title="Event for Proposal",
            start_time=event_start,
            end_time=event_end,
            offering_id=offering_id,
            teacher_id=teacher_id,
            status=EventStatus.SCHEDULED,
        ))
        await s.commit()

    teacher_cookie = sign_session({"user_id": str(teacher_id)})
    admin_cookie = sign_session({"user_id": str(admin_id)})

    yield {
        "teacher_id": teacher_id,
        "admin_id": admin_id,
        "offering_id": offering_id,
        "event_id": event_id,
        "event_start": event_start,
        "event_end": event_end,
        "teacher_cookie": teacher_cookie,
        "admin_cookie": admin_cookie,
    }

    async with factory() as s:
        # Delete proposals first (FK child of event)
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == event_id)
        )
        for p in res.scalars().all():
            await s.delete(p)
        await s.flush()

        ev = await s.get(ScheduleEvent, event_id)
        if ev:
            await s.delete(ev)
        await s.flush()

        off = await s.get(Offering, offering_id)
        if off:
            await s.delete(off)
        await s.flush()

        t = await s.get(User, teacher_id)
        if t:
            await s.delete(t)
        a = await s.get(User, admin_id)
        if a:
            await s.delete(a)
        await s.commit()
    await engine.dispose()


# ── POST /teacher/proposals/create unauthenticated ────────────────────────────

async def test_create_proposal_unauthenticated_redirects(client):
    r = await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(uuid.uuid4()),
            "new_start": datetime.now(timezone.utc).isoformat(),
            "new_end": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        },
    )
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


# ── Full workflow: teacher creates → admin approves ───────────────────────────

async def test_teacher_creates_proposal_successfully(client, proposal_env):
    env = proposal_env
    cookie = env["teacher_cookie"]
    csrf = _csrf_token_for(cookie)

    new_start = env["event_start"] + timedelta(days=1)
    new_end = new_start + timedelta(hours=1)

    r = await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    # Returns inline_success.html fragment
    assert r.status_code == 200
    assert "Propozycja" in r.text


async def test_proposal_is_created_as_pending(client, proposal_env):
    env = proposal_env
    cookie = env["teacher_cookie"]
    csrf = _csrf_token_for(cookie)

    new_start = env["event_start"] + timedelta(days=1)
    new_end = new_start + timedelta(hours=1)

    await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )

    # Verify in DB
    from app.models.proposals import RescheduleProposal
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == env["event_id"])
        )
        proposals = res.scalars().all()
    await engine.dispose()

    assert len(proposals) >= 1
    assert proposals[-1].status == ProposalStatus.PENDING


# ── Full workflow: teacher creates → admin approves ───────────────────────────

async def test_admin_approves_proposal_updates_status(client, proposal_env):
    env = proposal_env
    teacher_cookie = env["teacher_cookie"]
    admin_cookie = env["admin_cookie"]
    teacher_csrf = _csrf_token_for(teacher_cookie)
    admin_csrf = _csrf_token_for(admin_cookie)

    new_start = env["event_start"] + timedelta(days=1)
    new_end = new_start + timedelta(hours=1)

    # Teacher creates proposal
    await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": teacher_csrf},
    )

    # Get proposal id from DB
    from app.models.proposals import RescheduleProposal
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == env["event_id"])
        )
        proposal = res.scalars().first()
    await engine.dispose()
    assert proposal is not None

    # Admin approves
    r = await client.post(
        f"/admin/proposals/{proposal.id}/approve",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 200

    # Verify status in DB
    engine2 = _engine()
    factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with factory2() as s:
        updated = await s.get(RescheduleProposal, proposal.id)
    await engine2.dispose()
    assert updated.status == ProposalStatus.APPROVED


async def test_approve_proposal_updates_event_times(client, proposal_env):
    env = proposal_env
    teacher_cookie = env["teacher_cookie"]
    admin_cookie = env["admin_cookie"]
    teacher_csrf = _csrf_token_for(teacher_cookie)
    admin_csrf = _csrf_token_for(admin_cookie)

    new_start = env["event_start"] + timedelta(days=2)
    new_end = new_start + timedelta(hours=1)

    await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": teacher_csrf},
    )

    from app.models.proposals import RescheduleProposal
    from app.models.scheduling import ScheduleEvent
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == env["event_id"])
        )
        proposal = res.scalars().first()
    await engine.dispose()

    await client.post(
        f"/admin/proposals/{proposal.id}/approve",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": admin_csrf},
    )

    engine2 = _engine()
    factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with factory2() as s:
        ev = await s.get(ScheduleEvent, env["event_id"])
    await engine2.dispose()

    # Event times should have been updated to the proposed times
    assert ev.start_time.replace(tzinfo=timezone.utc) == new_start.replace(tzinfo=timezone.utc)


# ── Full workflow: teacher creates → admin rejects ────────────────────────────

async def test_admin_rejects_proposal_updates_status(client, proposal_env):
    env = proposal_env
    teacher_cookie = env["teacher_cookie"]
    admin_cookie = env["admin_cookie"]
    teacher_csrf = _csrf_token_for(teacher_cookie)
    admin_csrf = _csrf_token_for(admin_cookie)

    new_start = env["event_start"] + timedelta(days=3)
    new_end = new_start + timedelta(hours=1)

    # Teacher creates proposal
    await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": teacher_csrf},
    )

    from app.models.proposals import RescheduleProposal
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == env["event_id"])
        )
        proposal = res.scalars().first()
    await engine.dispose()
    assert proposal is not None

    # Admin rejects
    r = await client.post(
        f"/admin/proposals/{proposal.id}/reject",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert r.status_code == 200

    # Verify status in DB
    engine2 = _engine()
    factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with factory2() as s:
        updated = await s.get(RescheduleProposal, proposal.id)
    await engine2.dispose()
    assert updated.status == ProposalStatus.REJECTED


async def test_rejected_proposal_event_times_unchanged(client, proposal_env):
    """Rejecting a proposal must NOT change the event's original times."""
    env = proposal_env
    teacher_cookie = env["teacher_cookie"]
    admin_cookie = env["admin_cookie"]
    teacher_csrf = _csrf_token_for(teacher_cookie)
    admin_csrf = _csrf_token_for(admin_cookie)

    new_start = env["event_start"] + timedelta(days=4)
    new_end = new_start + timedelta(hours=1)
    original_start = env["event_start"]

    await client.post(
        "/teacher/proposals/create",
        data={
            "event_id": str(env["event_id"]),
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
        },
        cookies={"session": teacher_cookie},
        headers={"X-CSRF-Token": teacher_csrf},
    )

    from app.models.proposals import RescheduleProposal
    from app.models.scheduling import ScheduleEvent
    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        res = await s.execute(
            select(RescheduleProposal).where(RescheduleProposal.event_id == env["event_id"])
        )
        proposal = res.scalars().first()
    await engine.dispose()

    await client.post(
        f"/admin/proposals/{proposal.id}/reject",
        cookies={"session": admin_cookie},
        headers={"X-CSRF-Token": admin_csrf},
    )

    engine2 = _engine()
    factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
    async with factory2() as s:
        ev = await s.get(ScheduleEvent, env["event_id"])
    await engine2.dispose()

    # Start time should be unchanged (same as original)
    assert ev.start_time == original_start or abs(
        (ev.start_time - original_start).total_seconds()
    ) < 2
