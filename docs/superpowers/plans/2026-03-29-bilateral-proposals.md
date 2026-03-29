# Bilateral Reschedule Proposals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the admin-gated `RescheduleProposal` system with a bilateral `EventChangeRequest` model where teacher and student negotiate schedule changes directly; admin receives only a passive badge count.

**Architecture:** New `EventChangeRequest` SQLAlchemy model with explicit proposer/responder semantics. Six JSON API endpoints under `/api/change-requests`. Old admin approve/reject routes and `reschedule_proposals` table are dropped in two sequential migrations so rollback is clean. Templates updated to show incoming/outgoing proposals with HTMX inline actions.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Jinja2/HTMX, Resend (email)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/models/change_requests.py` | Create | `EventChangeRequest` ORM model + `ChangeRequestStatus` enum |
| `app/schemas/change_requests.py` | Create | `EventChangeRequestCreate` + `EventChangeRequestRead` Pydantic schemas |
| `app/api/routes_change_requests.py` | Create | All 6 API endpoints |
| `app/main.py` | Modify | Register new router |
| `app/services/email.py` | Modify | Replace 2 stubs with real HTML implementations |
| `app/api/routes_admin.py` | Modify | Remove 3 proposals routes + `_pending_count` helper + `pending_proposals` context |
| `app/api/routes_teacher.py` | Modify | Replace proposals route with new model; remove old imports |
| `app/api/routes_student.py` | Modify | Add `/student/proposals` route |
| `app/templates/admin/proposals.html` | Delete | Replaced by badge-only UI |
| `app/templates/teacher/proposals.html` | Rewrite | Two-section incoming/outgoing layout |
| `app/templates/student/proposals.html` | Create | Same layout as teacher proposals |
| `app/templates/components/change_request_form.html` | Create | HTMX inline form fragment |
| `app/templates/components/navbar_teacher.html` | Create | Teacher nav with proposals badge |
| `app/templates/components/navbar_admin.html` | Modify | HTMX badge replacing `pending_proposals` |
| `app/templates/components/navbar_student.html` | Modify | Add proposals link + badge |
| `app/templates/teacher/dashboard.html` | Modify | Propose button + use new navbar |
| `app/templates/student/dashboard.html` | Modify | Propose button + use navbar |
| `alembic/versions/xxxx_add_event_change_requests.py` | Create | Migration 1: add new table |
| `alembic/versions/xxxx_drop_reschedule_proposals.py` | Create | Migration 2: drop old table |
| `tests/test_change_requests.py` | Create | Full test suite |

---

### Task 1: EventChangeRequest Model

**Files:**
- Create: `app/models/change_requests.py`

- [ ] **Step 1: Write the failing import test**

```python
# tests/test_change_requests.py
"""Bilateral reschedule proposal tests."""

def test_model_imports():
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    assert ChangeRequestStatus.PENDING == "pending"
    assert ChangeRequestStatus.ACCEPTED == "accepted"
    assert ChangeRequestStatus.REJECTED == "rejected"
    assert ChangeRequestStatus.CANCELLED == "cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_model_imports -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the model**

Create `app/models/change_requests.py`:

```python
"""EventChangeRequest ORM model."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.scheduling import ScheduleEvent


class ChangeRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class EventChangeRequest(Base):
    """A bilateral request to reschedule an event — either party may initiate."""

    __tablename__ = "event_change_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_events.id", ondelete="CASCADE"), nullable=False
    )
    proposer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    responder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    new_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ChangeRequestStatus] = mapped_column(
        SAEnum(ChangeRequestStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ChangeRequestStatus.PENDING,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    proposer: Mapped["User"] = relationship("User", foreign_keys=[proposer_id])
    responder: Mapped["User"] = relationship("User", foreign_keys=[responder_id])
    event: Mapped["ScheduleEvent"] = relationship(
        "ScheduleEvent", foreign_keys=[event_id]
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_model_imports -v
```
Expected: PASS

- [ ] **Step 5: Create Alembic migration (add table)**

First check the current alembic head:
```bash
docker-compose exec web alembic current
```

Then generate the migration:
```bash
docker-compose exec web alembic revision --autogenerate -m "add_event_change_requests_table"
```

Open the generated file in `alembic/versions/`. Verify it contains a `create_table("event_change_requests", ...)` call with all columns. If autogenerate missed anything, add it manually.

The migration should look like:
```python
"""add_event_change_requests_table

Revision ID: <generated>
Revises: <current_head>
Create Date: ...
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.create_table(
        "event_change_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("proposer_id", sa.UUID(), nullable=False),
        sa.Column("responder_id", sa.UUID(), nullable=False),
        sa.Column("new_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "rejected", "cancelled",
                    name="changerequeststatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["schedule_events.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["responder_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ecr_event_id", "event_change_requests", ["event_id"])
    op.create_index("ix_ecr_proposer_id", "event_change_requests", ["proposer_id"])
    op.create_index("ix_ecr_responder_id", "event_change_requests", ["responder_id"])

def downgrade() -> None:
    op.drop_index("ix_ecr_responder_id", table_name="event_change_requests")
    op.drop_index("ix_ecr_proposer_id", table_name="event_change_requests")
    op.drop_index("ix_ecr_event_id", table_name="event_change_requests")
    op.drop_table("event_change_requests")
    op.execute("DROP TYPE IF EXISTS changerequeststatus")
```

- [ ] **Step 6: Run the migration**

```bash
docker-compose exec web alembic upgrade head
```
Expected: no errors. Verify with:
```bash
docker-compose exec web alembic current
```

- [ ] **Step 7: Commit**

```bash
git add app/models/change_requests.py alembic/versions/
git commit -m "feat(proposals): add EventChangeRequest model and migration"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `app/schemas/change_requests.py`

- [ ] **Step 1: Write the failing import test**

Add to `tests/test_change_requests.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_schema_imports -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create schemas**

Create `app/schemas/change_requests.py`:

```python
"""Pydantic schemas for EventChangeRequest."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.change_requests import ChangeRequestStatus


class EventChangeRequestCreate(BaseModel):
    """Payload for creating a new change request. Backend derives responder_id."""
    event_id: uuid.UUID
    new_start: datetime
    new_end: datetime
    note: str | None = None


class EventChangeRequestRead(BaseModel):
    """Full representation returned to the client."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    proposer_id: uuid.UUID
    responder_id: uuid.UUID
    new_start: datetime
    new_end: datetime
    note: str | None
    status: ChangeRequestStatus
    created_at: datetime
    resolved_at: datetime | None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_schema_imports -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/change_requests.py tests/test_change_requests.py
git commit -m "feat(proposals): add EventChangeRequest Pydantic schemas"
```

---

### Task 3: POST /api/change-requests — Create Request

**Files:**
- Create: `app/api/routes_change_requests.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_change_requests.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_teacher_can_create_change_request tests/test_change_requests.py::test_student_can_create_change_request tests/test_change_requests.py::test_unrelated_user_cannot_create_change_request -v
```
Expected: FAIL with `404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Create the routes file with POST endpoint**

Create `app/api/routes_change_requests.py`:

```python
"""Bilateral reschedule proposal API routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_db
from app.core.auth import require_auth
from app.core.csrf import require_csrf
from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
from app.models.scheduling import ScheduleEvent
from app.models.users import User, UserRole
from app.schemas.change_requests import EventChangeRequestCreate, EventChangeRequestRead

router = APIRouter(prefix="/api/change-requests", tags=["change-requests"])


@router.post("", response_model=EventChangeRequestRead, status_code=201)
async def create_change_request(
    payload: EventChangeRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> EventChangeRequest:
    """Teacher or student creates a reschedule request for an event they belong to."""
    event = (await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == payload.event_id)
    )).scalar_one_or_none()

    if event is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zajęć.")

    if event.student_id is None:
        raise HTTPException(
            status_code=422,
            detail="Nie można zaproponować zmiany dla zajęć bez przypisanego ucznia.",
        )

    # Determine proposer / responder from the event parties.
    if current_user.id == event.teacher_id:
        responder_id = event.student_id
    elif current_user.id == event.student_id:
        responder_id = event.teacher_id
    else:
        raise HTTPException(status_code=403, detail="Brak uprawnień.")

    cr = EventChangeRequest(
        event_id=payload.event_id,
        proposer_id=current_user.id,
        responder_id=responder_id,
        new_start=payload.new_start,
        new_end=payload.new_end,
        note=payload.note,
        status=ChangeRequestStatus.PENDING,
    )
    db.add(cr)
    await db.flush()

    # Send email to responder (fire-and-forget — email failure must not fail the request).
    try:
        from app.services.email import send_change_request_email
        await send_change_request_email(cr, event)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to send change request email for cr_id=%s", cr.id
        )

    return cr
```

- [ ] **Step 4: Register the router in main.py**

In `app/main.py`, add the import and include:

```python
# Add to existing imports at the top:
from app.api import routes_change_requests

# Add after the existing include_router lines:
app.include_router(routes_change_requests.router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_teacher_can_create_change_request tests/test_change_requests.py::test_student_can_create_change_request tests/test_change_requests.py::test_unrelated_user_cannot_create_change_request -v
```
Expected: all 3 PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/routes_change_requests.py app/main.py tests/test_change_requests.py
git commit -m "feat(proposals): add POST /api/change-requests endpoint"
```

---

### Task 4: PATCH Endpoints — Accept, Reject, Cancel

**Files:**
- Modify: `app/api/routes_change_requests.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_change_requests.py`:

```python
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
        # new_start is 2 hours after original
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_responder_can_accept tests/test_change_requests.py::test_proposer_cannot_accept tests/test_change_requests.py::test_accept_already_resolved_returns_409 tests/test_change_requests.py::test_responder_can_reject tests/test_change_requests.py::test_proposer_can_cancel -v
```
Expected: FAIL with 404

- [ ] **Step 3: Add PATCH endpoints to routes_change_requests.py**

Append to `app/api/routes_change_requests.py` (after the POST endpoint):

```python
async def _get_pending_request(db: AsyncSession, cr_id: UUID) -> EventChangeRequest:
    """Fetch a change request by ID; raise 404 if missing, 409 if not PENDING."""
    cr = (await db.execute(
        select(EventChangeRequest).where(EventChangeRequest.id == cr_id)
    )).scalar_one_or_none()
    if cr is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono prośby.")
    if cr.status != ChangeRequestStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="Prośba nie jest już oczekująca.",
        )
    return cr


@router.patch("/{cr_id}/accept", response_model=EventChangeRequestRead)
async def accept_change_request(
    cr_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> EventChangeRequest:
    """Responder accepts the request — event times are updated immediately."""
    cr = await _get_pending_request(db, cr_id)
    if current_user.id != cr.responder_id:
        raise HTTPException(status_code=403, detail="Tylko odbiorca może zaakceptować.")

    event = (await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == cr.event_id)
    )).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Zajęcia nie istnieją.")

    event.start_time = cr.new_start
    event.end_time = cr.new_end
    cr.status = ChangeRequestStatus.ACCEPTED
    cr.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    # Invalidate Redis cache if Plan 1 (calendar performance) has been implemented.
    try:
        from app.core.cache import invalidate_user as _cache_invalidate
        await _cache_invalidate(event.teacher_id, event.student_id)
    except ImportError:
        pass

    # Email proposer — failure must not fail the request.
    try:
        from app.services.email import send_change_request_outcome_email
        await send_change_request_outcome_email(cr, event, accepted=True)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to send accept email for cr_id=%s", cr_id
        )

    return cr


@router.patch("/{cr_id}/reject", response_model=EventChangeRequestRead)
async def reject_change_request(
    cr_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> EventChangeRequest:
    """Responder rejects the request."""
    cr = await _get_pending_request(db, cr_id)
    if current_user.id != cr.responder_id:
        raise HTTPException(status_code=403, detail="Tylko odbiorca może odrzucić.")

    cr.status = ChangeRequestStatus.REJECTED
    cr.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    event = (await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == cr.event_id)
    )).scalar_one_or_none()

    try:
        from app.services.email import send_change_request_outcome_email
        await send_change_request_outcome_email(cr, event, accepted=False)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to send reject email for cr_id=%s", cr_id
        )

    return cr


@router.patch("/{cr_id}/cancel", response_model=EventChangeRequestRead)
async def cancel_change_request(
    cr_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> EventChangeRequest:
    """Proposer cancels their own pending request."""
    cr = await _get_pending_request(db, cr_id)
    if current_user.id != cr.proposer_id:
        raise HTTPException(status_code=403, detail="Tylko wnioskodawca może anulować.")

    cr.status = ChangeRequestStatus.CANCELLED
    cr.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return cr
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_responder_can_accept tests/test_change_requests.py::test_proposer_cannot_accept tests/test_change_requests.py::test_accept_already_resolved_returns_409 tests/test_change_requests.py::test_responder_can_reject tests/test_change_requests.py::test_proposer_can_cancel -v
```
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_change_requests.py tests/test_change_requests.py
git commit -m "feat(proposals): add accept/reject/cancel PATCH endpoints"
```

---

### Task 5: GET Endpoints — List + Pending Count

**Files:**
- Modify: `app/api/routes_change_requests.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_change_requests.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_pending_count_for_teacher tests/test_change_requests.py::test_list_change_requests -v
```
Expected: FAIL with 404

- [ ] **Step 3: Add GET endpoints to routes_change_requests.py**

Append to `app/api/routes_change_requests.py`:

```python
@router.get("/pending-count", response_class=PlainTextResponse)
async def pending_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> str:
    """Returns the number of PENDING requests as plain text (for HTMX badge swap).

    Admin: all PENDING requests across all users.
    Teacher / Student: only requests where they are proposer or responder.
    """
    if current_user.role == UserRole.ADMIN:
        count = (await db.execute(
            select(func.count(EventChangeRequest.id))
            .where(EventChangeRequest.status == ChangeRequestStatus.PENDING)
        )).scalar_one()
    else:
        count = (await db.execute(
            select(func.count(EventChangeRequest.id))
            .where(
                EventChangeRequest.status == ChangeRequestStatus.PENDING,
                (
                    (EventChangeRequest.proposer_id == current_user.id) |
                    (EventChangeRequest.responder_id == current_user.id)
                ),
            )
        )).scalar_one()
    return str(count) if count else ""


@router.get("", response_model=list[EventChangeRequestRead])
async def list_change_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> list[EventChangeRequest]:
    """Returns all change requests involving the current user.

    Admin receives all requests (read-only view).
    Teacher / Student receive only requests where they are proposer or responder.
    """
    from sqlalchemy.orm import selectinload

    q = (
        select(EventChangeRequest)
        .options(
            selectinload(EventChangeRequest.proposer),
            selectinload(EventChangeRequest.responder),
            selectinload(EventChangeRequest.event),
        )
        .order_by(EventChangeRequest.created_at.desc())
    )
    if current_user.role != UserRole.ADMIN:
        q = q.where(
            (EventChangeRequest.proposer_id == current_user.id) |
            (EventChangeRequest.responder_id == current_user.id)
        )
    return (await db.execute(q)).scalars().all()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_pending_count_for_teacher tests/test_change_requests.py::test_list_change_requests -v
```
Expected: both PASS

- [ ] **Step 5: Run the full change-requests test suite so far**

```bash
docker-compose exec web pytest tests/test_change_requests.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/routes_change_requests.py tests/test_change_requests.py
git commit -m "feat(proposals): add list and pending-count GET endpoints"
```

---

### Task 6: Email Service — Replace Stubs

**Files:**
- Modify: `app/services/email.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_change_requests.py`:

```python
async def test_email_stubs_are_callable(cr_env):
    """Smoke test: email functions don't raise when RESEND_API_KEY is unset."""
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    from app.models.scheduling import ScheduleEvent, EventStatus
    from app.services.email import send_change_request_email, send_change_request_outcome_email
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    # Construct minimal mock objects — no DB needed for logging-only path
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

    # Should not raise (falls back to logging when RESEND_API_KEY is unset)
    await send_change_request_email(FakeCR(), FakeEvent())
    await send_change_request_outcome_email(FakeCR(), FakeEvent(), accepted=True)
    await send_change_request_outcome_email(FakeCR(), FakeEvent(), accepted=False)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_email_stubs_are_callable -v
```
Expected: FAIL because `send_change_request_email` doesn't exist (only `send_proposal_email`)

- [ ] **Step 3: Replace stubs in email.py**

In `app/services/email.py`, replace the two stubs at the bottom (`send_proposal_email` and `send_proposal_outcome_email`) with these implementations:

```python
# ---------------------------------------------------------------------------
# Change request emails (bilateral proposal system)
# ---------------------------------------------------------------------------

def _change_request_html(cr, event) -> str:
    """Email to responder: you have a new reschedule request."""
    from html import escape
    proposer_name = escape(cr.proposer.full_name)
    event_title = escape(event.title)
    new_start = cr.new_start.strftime("%d.%m.%Y %H:%M")
    new_end = cr.new_end.strftime("%H:%M")
    note_row = ""
    if cr.note:
        note_row = f"""
        <tr>
          <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">Wiadomość</td>
          <td style="padding:6px 0;color:#111827;font-size:13px">{escape(cr.note)}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Prośba o zmianę terminu — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Platforma korepetycji</p>
            <h1 style="margin:0;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">Ekorepetycje</h1>
          </td>
        </tr>
        <tr>
          <td style="background:#ffffff;padding:36px 40px">
            <p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#16a34a">Nowa prośba o zmianę</p>
            <h2 style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;line-height:1.3">
              {proposer_name} chce zmienić termin zajęć
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:28px">
              <tr>
                <td style="padding:20px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">Zajęcia</td>
                      <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{event_title}</td>
                    </tr>
                    <tr>
                      <td style="padding:6px 0;color:#6b7280;font-size:13px;vertical-align:top">Nowy termin</td>
                      <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{new_start} – {new_end}</td>
                    </tr>{note_row}
                  </table>
                </td>
              </tr>
            </table>
            <p style="margin:0;font-size:13px;color:#6b7280;line-height:1.6">
              Zaloguj się do platformy, aby zaakceptować lub odrzucić tę prośbę.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:11px;color:#9ca3af">Ekorepetycje — powiadomienie automatyczne.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _change_request_outcome_html(cr, event, accepted: bool) -> str:
    """Email to proposer: their request was accepted or rejected."""
    from html import escape
    responder_name = escape(cr.responder.full_name)
    event_title = escape(event.title)
    outcome_pl = "zaakceptowana" if accepted else "odrzucona"
    outcome_color = "#16a34a" if accepted else "#dc2626"
    time_row = ""
    if accepted:
        new_start = cr.new_start.strftime("%d.%m.%Y %H:%M")
        new_end = cr.new_end.strftime("%H:%M")
        time_row = f"""
        <tr>
          <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px">Nowy termin</td>
          <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{new_start} – {new_end}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Odpowiedź na prośbę o zmianę — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Platforma korepetycji</p>
            <h1 style="margin:0;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">Ekorepetycje</h1>
          </td>
        </tr>
        <tr>
          <td style="background:#ffffff;padding:36px 40px">
            <p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:{outcome_color}">
              Prośba {outcome_pl}
            </p>
            <h2 style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;line-height:1.3">
              {responder_name} {outcome_pl} Twoją prośbę
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:28px">
              <tr>
                <td style="padding:20px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px">Zajęcia</td>
                      <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{event_title}</td>
                    </tr>{time_row}
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:11px;color:#9ca3af">Ekorepetycje — powiadomienie automatyczne.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def send_change_request_email(cr, event) -> None:
    """Notify the responder that a change request has been created.

    Falls back to logging when RESEND_API_KEY is not set.
    """
    from app.core.config import settings

    if not settings.RESEND_API_KEY:
        logger.info(
            "Change request email [no RESEND_API_KEY] | to=%s | event=%s | new_start=%s",
            cr.responder.email, event.title, cr.new_start,
        )
        return

    import resend
    resend.api_key = settings.RESEND_API_KEY
    msg = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [cr.responder.email],
        "subject": f"Prośba o zmianę terminu: {event.title}",
        "html": _change_request_html(cr, event),
    }
    await asyncio.to_thread(resend.Emails.send, msg)
    logger.info("Change request email sent | to=%s", cr.responder.email)


async def send_change_request_outcome_email(cr, event, accepted: bool) -> None:
    """Notify the proposer of the outcome (accept/reject).

    Falls back to logging when RESEND_API_KEY is not set.
    """
    from app.core.config import settings

    outcome = "accepted" if accepted else "rejected"
    if not settings.RESEND_API_KEY:
        logger.info(
            "Change outcome email [no RESEND_API_KEY] | to=%s | outcome=%s",
            cr.proposer.email, outcome,
        )
        return

    import resend
    resend.api_key = settings.RESEND_API_KEY
    subject = (
        f"Termin zajęć zaktualizowany: {event.title}"
        if accepted
        else f"Prośba o zmianę odrzucona: {event.title}"
    )
    msg = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [cr.proposer.email],
        "subject": subject,
        "html": _change_request_outcome_html(cr, event, accepted),
    }
    await asyncio.to_thread(resend.Emails.send, msg)
    logger.info("Change outcome email sent | to=%s | outcome=%s",
                cr.proposer.email, outcome)
```

Also **remove** the old stub functions `send_proposal_email` and `send_proposal_outcome_email` from the file since nothing will reference them after this task.

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_email_stubs_are_callable -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email.py tests/test_change_requests.py
git commit -m "feat(proposals): replace email stubs with HTML change request emails"
```

---

### Task 7: Remove Admin Proposals Routes

**Files:**
- Modify: `app/api/routes_admin.py`

- [ ] **Step 1: Write a test verifying admin proposals routes are gone**

Add to `tests/test_change_requests.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails (routes still exist)**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_admin_cannot_approve_reject_proposals -v
```
Expected: FAIL (routes return 404 for nonexistent proposal, but the route itself exists → returns 200 with inline_success rather than 404)

Actually if the proposal doesn't exist the route currently returns 200 with inline_success (no-op). Let's check by running the test. If it actually returns 404 because the proposal doesn't exist, the test may accidentally pass. The real test is that the route path doesn't exist as a registered endpoint. We can verify with `GET /openapi.json`:

```bash
docker-compose exec web python -c "
from app.main import app
routes = [r.path for r in app.routes]
print([r for r in routes if 'proposal' in r])
"
```
Expected before cleanup: shows `/admin/proposals/{proposal_id}/approve` etc.

- [ ] **Step 3: Clean up routes_admin.py**

In `app/api/routes_admin.py` make these changes:

**a) Remove the import of `RescheduleProposal` and `ProposalStatus`:**
```python
# DELETE these lines:
from app.models.proposals import RescheduleProposal, ProposalStatus
```

**b) Remove the `_pending_count` helper function** (lines 25-29):
```python
# DELETE this entire function:
async def _pending_count(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count(RescheduleProposal.id))
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
    )).scalar_one()
```

**c) In `admin_dashboard`, remove the `pending_proposals` context:**
```python
# BEFORE:
    pending = await _pending_count(db)
    return templates.TemplateResponse(
        request, "admin/dashboard.html",
        {"teachers": teachers, "pending_proposals": pending},
    )

# AFTER:
    return templates.TemplateResponse(
        request, "admin/dashboard.html",
        {"teachers": teachers},
    )
```

Also remove `db: AsyncSession = Depends(get_db)` from `admin_dashboard` if it is no longer needed (check if teachers query is still there — it is, so keep db).

**d) In `admin_users`, remove `pending_proposals` from context everywhere it appears.** The function has three `TemplateResponse` calls. Remove `"pending_proposals": ...` from all three:
- In the success return: remove `"pending_proposals": await _pending_count(db)`
- In the error return: same
- In `create_user` success return: same

**e) Delete the three proposal route handlers** (starting at line 163):
```python
# DELETE these three entire route functions:
@router.get("/proposals", ...)
async def admin_proposals(...):
    ...

@router.post("/proposals/{proposal_id}/approve", ...)
async def approve_proposal(...):
    ...

@router.post("/proposals/{proposal_id}/reject", ...)
async def reject_proposal(...):
    ...
```

**f) Remove `func` from imports if no longer used** — check if `func` is still used elsewhere in the file (it is not after removing `_pending_count`). Remove it from `from sqlalchemy import select, func`.

The final import block in `routes_admin.py` should be:
```python
from sqlalchemy import select
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec web pytest tests/test_change_requests.py::test_admin_cannot_approve_reject_proposals -v
```
Expected: PASS (routes return 404)

- [ ] **Step 5: Run existing test suite to catch regressions**

```bash
docker-compose exec web pytest --tb=short -q
```
Expected: all existing tests pass. If admin template tests fail due to missing `pending_proposals` context variable, that is expected — we will fix the templates in Task 9.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes_admin.py tests/test_change_requests.py
git commit -m "feat(proposals): remove admin proposals routes and pending_proposals context"
```

---

### Task 8: Teacher Routes + Templates

**Files:**
- Modify: `app/api/routes_teacher.py`
- Rewrite: `app/templates/teacher/proposals.html`
- Modify: `app/templates/teacher/dashboard.html`
- Create: `app/templates/components/change_request_form.html`
- Create: `app/templates/components/navbar_teacher.html`

- [ ] **Step 1: Update routes_teacher.py**

Replace the entire content of `app/api/routes_teacher.py`:

```python
"""Teacher-facing HTML routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_teacher_or_admin
from app.core.templates import templates
from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/", response_class=HTMLResponse)
async def teacher_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleEvent)
        .where(
            ScheduleEvent.teacher_id == current_user.id,
            ScheduleEvent.start_time >= now,
            ScheduleEvent.status == EventStatus.SCHEDULED,
        )
        .options(selectinload(ScheduleEvent.student), selectinload(ScheduleEvent.offering))
        .order_by(ScheduleEvent.start_time)
        .limit(10)
    )
    upcoming = result.scalars().all()
    return templates.TemplateResponse(
        request, "teacher/dashboard.html",
        {"user": current_user, "upcoming": upcoming},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def teacher_calendar(
    request: Request,
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "teacher/calendar.html",
        {"user": current_user},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def teacher_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    result = await db.execute(
        select(EventChangeRequest)
        .where(
            or_(
                EventChangeRequest.proposer_id == current_user.id,
                EventChangeRequest.responder_id == current_user.id,
            )
        )
        .options(
            selectinload(EventChangeRequest.event),
            selectinload(EventChangeRequest.proposer),
            selectinload(EventChangeRequest.responder),
        )
        .order_by(EventChangeRequest.created_at.desc())
    )
    requests = result.scalars().all()
    incoming = [r for r in requests
                if r.responder_id == current_user.id
                and r.status == ChangeRequestStatus.PENDING]
    outgoing = [r for r in requests
                if r.proposer_id == current_user.id]
    return templates.TemplateResponse(
        request, "teacher/proposals.html",
        {
            "user": current_user,
            "incoming": incoming,
            "outgoing": outgoing,
        },
    )
```

- [ ] **Step 2: Rewrite teacher/proposals.html**

Replace entire content of `app/templates/teacher/proposals.html`:

```html
{% extends "base.html" %}

{% block navbar %}{% include "components/navbar_teacher.html" %}{% endblock %}

{% block title %}Propozycje — Ekorepetycje{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-6 max-w-5xl mx-auto">
    <div class="mb-8 flex items-center justify-between">
        <h1 class="text-3xl font-bold text-white">Propozycje zmiany terminu</h1>
        <a href="/teacher/" class="text-sm text-gray-400 hover:text-white">← Dashboard</a>
    </div>

    <!-- Incoming (responder) -->
    <section class="mb-10">
        <h2 class="text-xs font-medium text-gray-500 uppercase tracking-widest mb-4">Oczekujące na Twoją odpowiedź</h2>
        {% if not incoming %}
        <p class="text-gray-500 text-sm">Brak oczekujących próśb.</p>
        {% else %}
        <div class="space-y-3">
            {% for req in incoming %}
            <div id="cr-{{ req.id }}" class="bg-gray-900/50 border border-gray-800/50 rounded-2xl p-5 flex items-center justify-between">
                <div>
                    <p class="font-medium text-white">{{ req.event.title }}</p>
                    <p class="text-sm text-gray-400 mt-1">
                        {{ req.proposer.full_name }} proponuje:
                        {{ req.new_start.strftime('%d.%m.%Y %H:%M') }} – {{ req.new_end.strftime('%H:%M') }}
                    </p>
                    {% if req.note %}
                    <p class="text-xs text-gray-500 mt-1">"{{ req.note }}"</p>
                    {% endif %}
                </div>
                <div class="flex items-center gap-2 ml-4 shrink-0">
                    <button
                        hx-patch="/api/change-requests/{{ req.id }}/accept"
                        hx-target="#cr-{{ req.id }}"
                        hx-swap="outerHTML"
                        class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-3 py-1.5 rounded-lg text-xs transition-colors">
                        Akceptuj
                    </button>
                    <button
                        hx-patch="/api/change-requests/{{ req.id }}/reject"
                        hx-target="#cr-{{ req.id }}"
                        hx-swap="outerHTML"
                        class="border border-red-500/50 text-red-400 hover:text-red-300 px-3 py-1.5 rounded-lg text-xs transition-colors">
                        Odrzuć
                    </button>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </section>

    <!-- Outgoing (proposer) -->
    <section>
        <h2 class="text-xs font-medium text-gray-500 uppercase tracking-widest mb-4">Twoje wysłane prośby</h2>
        {% if not outgoing %}
        <p class="text-gray-500 text-sm">Nie wysłano jeszcze żadnych próśb.</p>
        {% else %}
        <div class="bg-gray-900/50 border border-gray-800/50 rounded-2xl overflow-hidden">
            <table class="w-full text-sm">
                <thead class="border-b border-gray-800/50">
                    <tr class="text-left text-xs text-gray-500 uppercase tracking-wide">
                        <th class="px-6 py-4">Zajęcia</th>
                        <th class="px-6 py-4">Proponowany termin</th>
                        <th class="px-6 py-4">Wysłano</th>
                        <th class="px-6 py-4">Status / Akcja</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/30">
                    {% for req in outgoing %}
                    <tr id="cr-out-{{ req.id }}" class="hover:bg-gray-800/20 transition-colors">
                        <td class="px-6 py-4 text-white">{{ req.event.title }}</td>
                        <td class="px-6 py-4 text-gray-300">
                            {{ req.new_start.strftime('%d.%m.%Y %H:%M') }} – {{ req.new_end.strftime('%H:%M') }}
                        </td>
                        <td class="px-6 py-4 text-gray-500">{{ req.created_at.strftime('%d.%m.%Y') }}</td>
                        <td class="px-6 py-4">
                            {% if req.status.value == 'pending' %}
                            <button
                                hx-patch="/api/change-requests/{{ req.id }}/cancel"
                                hx-target="#cr-out-{{ req.id }}"
                                hx-swap="outerHTML"
                                class="text-xs border border-gray-700 text-gray-400 hover:text-white px-3 py-1 rounded-lg transition-colors">
                                Anuluj
                            </button>
                            {% elif req.status.value == 'accepted' %}
                            <span class="px-2 py-1 text-xs font-medium bg-green-500/20 text-green-400 rounded-full">Zaakceptowana</span>
                            {% elif req.status.value == 'rejected' %}
                            <span class="px-2 py-1 text-xs font-medium bg-red-500/20 text-red-400 rounded-full">Odrzucona</span>
                            {% else %}
                            <span class="px-2 py-1 text-xs font-medium bg-gray-500/20 text-gray-400 rounded-full">Anulowana</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </section>
</div>
{% endblock %}
```

- [ ] **Step 3: Create the HTMX inline change request form fragment**

Create `app/templates/components/change_request_form.html`:

```html
<div class="bg-gray-800/50 border border-gray-700/50 rounded-2xl p-4 ml-6">
    <form hx-post="/api/change-requests"
          hx-target="closest div"
          hx-swap="outerHTML"
          hx-ext="json-enc"
          class="flex items-end gap-3 flex-wrap">
        <input type="hidden" name="event_id" value="{{ event.id }}">
        <div>
            <label class="block text-xs text-gray-400 mb-1">Nowy start</label>
            <input type="datetime-local" name="new_start" required
                   class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none">
        </div>
        <div>
            <label class="block text-xs text-gray-400 mb-1">Nowy koniec</label>
            <input type="datetime-local" name="new_end" required
                   class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none">
        </div>
        <div>
            <label class="block text-xs text-gray-400 mb-1">Wiadomość (opcjonalnie)</label>
            <input type="text" name="note" maxlength="500" placeholder="Krótka notatka..."
                   class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none w-44">
        </div>
        <button type="submit"
                class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-4 py-2 rounded-lg text-sm transition-colors">
            Wyślij
        </button>
    </form>
</div>
```

**Note:** The form posts JSON via `hx-ext="json-enc"`. The `new_start`/`new_end` datetime-local values are ISO strings which FastAPI parses as `datetime`. This matches the `EventChangeRequestCreate` schema.

- [ ] **Step 4: Create navbar_teacher.html**

Create `app/templates/components/navbar_teacher.html`:

```html
<nav class="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-gray-950/80 border-b border-gray-800/50">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/teacher/" class="text-xl font-semibold tracking-tight text-white hover:text-green-400 transition-colors">
            Ekorepetycje <span class="text-xs text-gray-500 font-normal ml-1">nauczyciel</span>
        </a>
        <div class="flex items-center gap-6">
            <a href="/teacher/" class="text-sm text-gray-400 hover:text-white transition-colors">Dashboard</a>
            <a href="/teacher/calendar" class="text-sm text-gray-400 hover:text-white transition-colors">Kalendarz</a>
            <a href="/teacher/proposals" class="relative text-sm text-gray-400 hover:text-white transition-colors">
                Propozycje
                <span hx-get="/api/change-requests/pending-count"
                      hx-trigger="load, every 60s"
                      hx-target="this"
                      hx-swap="innerHTML"
                      class="absolute -top-1 -right-3 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full hidden [&:not(:empty)]:flex">
                </span>
            </a>
            <a href="/profile" class="text-sm text-gray-400 hover:text-white transition-colors">Profil</a>
            <form method="post" action="/logout" class="inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token(request) }}">
                <button class="text-sm text-gray-500 hover:text-white transition-colors">Wyloguj</button>
            </form>
        </div>
    </div>
</nav>
```

- [ ] **Step 5: Update teacher/dashboard.html**

In `app/templates/teacher/dashboard.html`:

**a) Add the navbar block** right after `{% extends "base.html" %}`:
```html
{% block navbar %}{% include "components/navbar_teacher.html" %}{% endblock %}
```

**b) Update the "Zaproponuj zmianę" button** to show/hide the new form fragment. Replace the existing proposal form section (the `<button>` + the hidden `<div>` below each event card) with:

```html
<!-- Replace the existing button + hidden proposal form div with: -->
<button onclick="document.getElementById('proposal-{{ event.id }}').classList.toggle('hidden')"
        class="text-xs border border-gray-700 text-gray-400 hover:text-white px-3 py-1.5 rounded-lg transition-colors">
    Zaproponuj zmianę
</button>
```

And replace the hidden proposal div:

```html
<!-- Proposal form (hidden by default) -->
<div id="proposal-{{ event.id }}" class="hidden">
    {% with event=event %}
    {% include "components/change_request_form.html" %}
    {% endwith %}
</div>
```

**c) Remove the old header nav links** (the "Moje propozycje" link and logout button in the page header) since navbar_teacher.html now handles navigation. The header section becomes just:
```html
<div class="mb-8 flex items-center justify-between">
    <div>
        <h1 class="text-3xl font-bold text-white">Witaj, {{ user.full_name }}!</h1>
        <p class="text-gray-400 mt-1">Twoje nadchodzące zajęcia</p>
    </div>
</div>
```

- [ ] **Step 6: Add navbar block to teacher/calendar.html**

In `app/templates/teacher/calendar.html`, add immediately after `{% extends "base.html" %}`:
```html
{% block navbar %}{% include "components/navbar_teacher.html" %}{% endblock %}
```

- [ ] **Step 7: Verify teacher dashboard renders**

```bash
docker-compose up -d && sleep 3
```
Then confirm no template errors in logs:
```bash
docker-compose logs web | tail -20
```

- [ ] **Step 8: Commit**

```bash
git add app/api/routes_teacher.py \
        app/templates/teacher/proposals.html \
        app/templates/teacher/dashboard.html \
        app/templates/teacher/calendar.html \
        app/templates/components/change_request_form.html \
        app/templates/components/navbar_teacher.html
git commit -m "feat(proposals): update teacher routes and templates for bilateral proposals"
```

---

### Task 9: Student Routes + Templates

**Files:**
- Modify: `app/api/routes_student.py`
- Create: `app/templates/student/proposals.html`
- Modify: `app/templates/student/dashboard.html`
- Modify: `app/templates/components/navbar_student.html`

- [ ] **Step 1: Add student proposals route**

Replace the entire content of `app/api/routes_student.py`:

```python
"""Student-facing HTML routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_role
from app.core.templates import templates
from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User, UserRole

router = APIRouter(prefix="/student", tags=["student"])


@router.get("/calendar", response_class=HTMLResponse)
async def student_calendar(
    request: Request,
    current_user: User = Depends(require_role(UserRole.STUDENT)),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "student/calendar.html",
        {"user": current_user},
    )


@router.get("/", response_class=HTMLResponse)
async def student_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STUDENT)),
) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleEvent)
        .where(ScheduleEvent.student_id == current_user.id)
        .options(selectinload(ScheduleEvent.teacher), selectinload(ScheduleEvent.offering))
        .order_by(ScheduleEvent.start_time.desc())
    )
    events = result.scalars().all()
    upcoming = [e for e in events if e.start_time >= now and e.status == EventStatus.SCHEDULED]
    past = [e for e in events if e.start_time < now]
    return templates.TemplateResponse(
        request, "student/dashboard.html",
        {"user": current_user, "upcoming": upcoming, "past": past},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def student_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STUDENT)),
) -> HTMLResponse:
    result = await db.execute(
        select(EventChangeRequest)
        .where(
            or_(
                EventChangeRequest.proposer_id == current_user.id,
                EventChangeRequest.responder_id == current_user.id,
            )
        )
        .options(
            selectinload(EventChangeRequest.event),
            selectinload(EventChangeRequest.proposer),
            selectinload(EventChangeRequest.responder),
        )
        .order_by(EventChangeRequest.created_at.desc())
    )
    requests = result.scalars().all()
    incoming = [r for r in requests
                if r.responder_id == current_user.id
                and r.status == ChangeRequestStatus.PENDING]
    outgoing = [r for r in requests
                if r.proposer_id == current_user.id]
    return templates.TemplateResponse(
        request, "student/proposals.html",
        {
            "user": current_user,
            "incoming": incoming,
            "outgoing": outgoing,
        },
    )
```

- [ ] **Step 2: Create student/proposals.html**

Create `app/templates/student/proposals.html`:

```html
{% extends "base.html" %}

{% block html_attrs %}class=""{% endblock %}
{% block body_attrs %}class="bg-gray-950 min-h-screen flex flex-col font-sans text-white"{% endblock %}
{% block navbar %}{% include "components/navbar_student.html" %}{% endblock %}
{% block footer %}{% endblock %}

{% block title %}Propozycje — Ekorepetycje{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-6 max-w-4xl mx-auto">
    <div class="mb-8 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-white">Propozycje zmiany terminu</h1>
        <a href="/student/" class="text-sm text-gray-400 hover:text-white">← Moje zajęcia</a>
    </div>

    <!-- Incoming (responder) -->
    <section class="mb-10">
        <h2 class="text-xs font-medium text-gray-500 uppercase tracking-widest mb-4">Oczekujące na Twoją odpowiedź</h2>
        {% if not incoming %}
        <p class="text-gray-500 text-sm">Brak oczekujących próśb.</p>
        {% else %}
        <div class="space-y-3">
            {% for req in incoming %}
            <div id="cr-{{ req.id }}" class="bg-gray-900/50 border border-gray-800/50 rounded-xl p-5 flex items-center justify-between">
                <div>
                    <p class="font-medium text-white">{{ req.event.title }}</p>
                    <p class="text-sm text-gray-400 mt-1">
                        {{ req.proposer.full_name }} proponuje:
                        {{ req.new_start.strftime('%d.%m.%Y %H:%M') }} – {{ req.new_end.strftime('%H:%M') }}
                    </p>
                    {% if req.note %}
                    <p class="text-xs text-gray-500 mt-1">"{{ req.note }}"</p>
                    {% endif %}
                </div>
                <div class="flex items-center gap-2 ml-4 shrink-0">
                    <button
                        hx-patch="/api/change-requests/{{ req.id }}/accept"
                        hx-target="#cr-{{ req.id }}"
                        hx-swap="outerHTML"
                        class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-3 py-1.5 rounded-lg text-xs transition-colors">
                        Akceptuj
                    </button>
                    <button
                        hx-patch="/api/change-requests/{{ req.id }}/reject"
                        hx-target="#cr-{{ req.id }}"
                        hx-swap="outerHTML"
                        class="border border-red-500/50 text-red-400 hover:text-red-300 px-3 py-1.5 rounded-lg text-xs transition-colors">
                        Odrzuć
                    </button>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </section>

    <!-- Outgoing (proposer) -->
    <section>
        <h2 class="text-xs font-medium text-gray-500 uppercase tracking-widest mb-4">Twoje wysłane prośby</h2>
        {% if not outgoing %}
        <p class="text-gray-500 text-sm">Nie wysłano jeszcze żadnych próśb.</p>
        {% else %}
        <div class="bg-gray-900/50 border border-gray-800/50 rounded-xl overflow-hidden">
            <table class="w-full text-sm">
                <thead class="border-b border-gray-800/50">
                    <tr class="text-left text-xs text-gray-500 uppercase tracking-wide">
                        <th class="px-5 py-4">Zajęcia</th>
                        <th class="px-5 py-4">Proponowany termin</th>
                        <th class="px-5 py-4">Status / Akcja</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/30">
                    {% for req in outgoing %}
                    <tr id="cr-out-{{ req.id }}" class="hover:bg-gray-800/20 transition-colors">
                        <td class="px-5 py-4 text-white">{{ req.event.title }}</td>
                        <td class="px-5 py-4 text-gray-300">
                            {{ req.new_start.strftime('%d.%m.%Y %H:%M') }} – {{ req.new_end.strftime('%H:%M') }}
                        </td>
                        <td class="px-5 py-4">
                            {% if req.status.value == 'pending' %}
                            <button
                                hx-patch="/api/change-requests/{{ req.id }}/cancel"
                                hx-target="#cr-out-{{ req.id }}"
                                hx-swap="outerHTML"
                                class="text-xs border border-gray-700 text-gray-400 hover:text-white px-3 py-1 rounded-lg transition-colors">
                                Anuluj
                            </button>
                            {% elif req.status.value == 'accepted' %}
                            <span class="px-2 py-1 text-xs font-medium bg-green-500/20 text-green-400 rounded-full">Zaakceptowana</span>
                            {% elif req.status.value == 'rejected' %}
                            <span class="px-2 py-1 text-xs font-medium bg-red-500/20 text-red-400 rounded-full">Odrzucona</span>
                            {% else %}
                            <span class="px-2 py-1 text-xs font-medium bg-gray-500/20 text-gray-400 rounded-full">Anulowana</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </section>
</div>
{% endblock %}
```

- [ ] **Step 3: Add propose button to student/dashboard.html**

In `app/templates/student/dashboard.html`, in the upcoming events loop, replace the closing `</div>` of each event card's right column with:

Find this section inside the `{% for event in upcoming %}` loop:
```html
<span class="px-2 py-1 text-xs font-medium bg-green-500/15 text-green-400 rounded-full">Zaplanowane</span>
```

Replace with:
```html
<div class="flex items-center gap-2">
    <span class="px-2 py-1 text-xs font-medium bg-green-500/15 text-green-400 rounded-full">Zaplanowane</span>
    <button onclick="document.getElementById('proposal-s-{{ event.id }}').classList.toggle('hidden')"
            class="text-xs border border-gray-700 text-gray-400 hover:text-white px-3 py-1.5 rounded-lg transition-colors">
        Zaproponuj zmianę
    </button>
</div>
```

Then add the hidden form fragment directly after the closing `</div>` of the event card:
```html
<div id="proposal-s-{{ event.id }}" class="hidden">
    {% with event=event %}
    {% include "components/change_request_form.html" %}
    {% endwith %}
</div>
```

- [ ] **Step 4: Update navbar_student.html**

Replace the content of `app/templates/components/navbar_student.html`:

```html
<nav class="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-gray-950/80 border-b border-gray-800/50">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/" class="text-xl font-semibold tracking-tight text-white hover:text-green-400 transition-colors">Ekorepetycje</a>
        <div class="flex items-center gap-4">
            <a href="/student/" class="text-sm text-gray-400 hover:text-white transition-colors">Moje zajęcia</a>
            <a href="/student/calendar" class="text-sm text-gray-400 hover:text-white transition-colors">Kalendarz</a>
            <a href="/student/proposals" class="relative text-sm text-gray-400 hover:text-white transition-colors">
                Propozycje
                <span hx-get="/api/change-requests/pending-count"
                      hx-trigger="load, every 60s"
                      hx-target="this"
                      hx-swap="innerHTML"
                      class="absolute -top-1 -right-3 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full hidden [&:not(:empty)]:flex">
                </span>
            </a>
            <a href="/profile" class="text-sm text-gray-400 hover:text-white transition-colors">Profil</a>
            <span class="text-sm text-gray-500">{{ user.full_name }}</span>
            <form method="post" action="/logout" class="inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token(request) }}">
                <button class="text-sm text-gray-400 hover:text-white transition-colors">Wyloguj</button>
            </form>
        </div>
    </div>
</nav>
```

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_student.py \
        app/templates/student/proposals.html \
        app/templates/student/dashboard.html \
        app/templates/components/navbar_student.html
git commit -m "feat(proposals): add student proposals route, templates, and navbar badge"
```

---

### Task 10: Admin Navbar Badge

**Files:**
- Modify: `app/templates/components/navbar_admin.html`

- [ ] **Step 1: Update admin navbar**

Replace the content of `app/templates/components/navbar_admin.html`:

```html
<nav class="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-gray-950/80 border-b border-gray-800/50">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/admin/" class="text-xl font-semibold tracking-tight text-white hover:text-green-400 transition-colors">
            Ekorepetycje <span class="text-xs text-gray-500 font-normal ml-1">admin</span>
        </a>
        <div class="flex items-center gap-6">
            <a href="/admin/" class="text-sm text-gray-400 hover:text-white transition-colors">Dashboard</a>
            <a href="/admin/users" class="text-sm text-gray-400 hover:text-white transition-colors">Użytkownicy</a>
            <a href="/admin/calendar" class="text-sm text-gray-400 hover:text-white transition-colors">Kalendarz</a>
            <!-- Passive badge: count of pending change requests — admin takes no action -->
            <span class="relative text-sm text-gray-400">
                Zmiany
                <span hx-get="/api/change-requests/pending-count"
                      hx-trigger="load, every 60s"
                      hx-target="this"
                      hx-swap="innerHTML"
                      class="absolute -top-1 -right-3 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full hidden [&:not(:empty)]:flex">
                </span>
            </span>
            <form method="post" action="/logout" class="inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token(request) }}">
                <button class="text-sm text-gray-500 hover:text-white transition-colors">Wyloguj</button>
            </form>
        </div>
    </div>
</nav>
```

- [ ] **Step 2: Verify admin templates that used pending_proposals don't error**

The admin templates (`admin/dashboard.html`, `admin/users.html`) may still reference `{{ pending_proposals }}`. Check:

```bash
grep -r "pending_proposals" app/templates/
```

For any remaining references, either remove the `{% if pending_proposals %}` block entirely or replace with the HTMX badge approach. The admin navbar now handles the badge — no template-level variable needed. Remove any `pending_proposals` references from `admin/dashboard.html` and `admin/users.html`.

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
docker-compose exec web pytest --tb=short -q
```
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add app/templates/components/navbar_admin.html app/templates/admin/
git commit -m "feat(proposals): update admin navbar to HTMX badge, remove pending_proposals context"
```

---

### Task 11: Migration 2 — Drop reschedule_proposals + Remove Old Model

**Files:**
- Create: `alembic/versions/xxxx_drop_reschedule_proposals.py`
- Delete: references to `app/models/proposals.py` (the file itself can stay or be deleted)

This task runs last because `reschedule_proposals` can be dropped safely only after the new system is verified.

- [ ] **Step 1: Verify no code references RescheduleProposal anymore**

```bash
grep -r "RescheduleProposal\|reschedule_proposals\|send_proposal_email\|send_proposal_outcome_email" \
    app/api/ app/services/ app/models/
```
Expected: no matches (routes_admin.py and routes_teacher.py were cleaned in earlier tasks; email.py stubs were replaced in Task 6).

If any matches remain, fix them before continuing.

- [ ] **Step 2: Generate the drop migration**

```bash
docker-compose exec web alembic revision -m "drop_reschedule_proposals_table"
```

Open the generated file and write the body manually (autogenerate won't detect the drop since the model import was removed):

```python
"""drop_reschedule_proposals_table

Revision ID: <generated>
Revises: <revision_id_of_migration_1>
Create Date: ...
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.drop_table("reschedule_proposals")
    op.execute("DROP TYPE IF EXISTS proposalstatus")

def downgrade() -> None:
    op.create_table(
        "reschedule_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("proposed_by", sa.UUID(), nullable=False),
        sa.Column("new_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="proposalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["schedule_events.id"]),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
```

**Important:** The `Revises:` field must point to the revision ID of migration 1 (the `add_event_change_requests_table` migration created in Task 1), not back to `698e615463d4`. Check with:
```bash
docker-compose exec web alembic history
```

- [ ] **Step 3: Run migration 2**

```bash
docker-compose exec web alembic upgrade head
```
Expected: `reschedule_proposals` table is dropped. Verify:
```bash
docker-compose exec web alembic current
```

- [ ] **Step 4: Delete the old model file**

```bash
rm app/models/proposals.py
```

- [ ] **Step 5: Delete the admin proposals template**

```bash
rm app/templates/admin/proposals.html
```

- [ ] **Step 6: Run full test suite**

```bash
docker-compose exec web pytest --tb=short -q
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/
git rm app/models/proposals.py app/templates/admin/proposals.html
git commit -m "feat(proposals): drop reschedule_proposals table and remove old model"
```

---

### Task 12: Final Test Run + Push

- [ ] **Step 1: Run the complete change-requests test suite**

```bash
docker-compose exec web pytest tests/test_change_requests.py -v
```
Expected output (all PASS):
```
test_model_imports PASSED
test_schema_imports PASSED
test_teacher_can_create_change_request PASSED
test_student_can_create_change_request PASSED
test_unrelated_user_cannot_create_change_request PASSED
test_responder_can_accept PASSED
test_proposer_cannot_accept PASSED
test_accept_already_resolved_returns_409 PASSED
test_responder_can_reject PASSED
test_proposer_can_cancel PASSED
test_pending_count_for_teacher PASSED
test_list_change_requests PASSED
test_email_stubs_are_callable PASSED
test_admin_cannot_approve_reject_proposals PASSED
```

- [ ] **Step 2: Run the full suite**

```bash
docker-compose exec web pytest --tb=short -q
```
Expected: all existing tests still pass alongside the new ones.

- [ ] **Step 3: Push to remote**

```bash
git push origin main
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ `EventChangeRequest` model with all fields (Task 1)
- ✅ Two Alembic migrations — add new, drop old — separate revisions (Tasks 1, 11)
- ✅ `EventChangeRequestCreate` + `EventChangeRequestRead` schemas (Task 2)
- ✅ `POST /api/change-requests` — derive responder, 422 if no student (Task 3)
- ✅ `PATCH accept/reject/cancel` with correct auth rules (Task 4)
- ✅ `GET /api/change-requests` + `GET /api/change-requests/pending-count` (Task 5)
- ✅ Email functions with Resend / log-fallback pattern (Task 6)
- ✅ Remove admin proposals routes (GET, approve, reject) (Task 7)
- ✅ Teacher proposals route uses new model (Task 8)
- ✅ Teacher proposals template — incoming/outgoing two sections (Task 8)
- ✅ Teacher dashboard — "Zaproponuj zmianę" button + HTMX form (Task 8)
- ✅ Student proposals route (Task 9)
- ✅ Student proposals template (Task 9)
- ✅ Student dashboard — "Zaproponuj zmianę" button (Task 9)
- ✅ Student navbar — "Propozycje" link + HTMX badge (Task 9)
- ✅ Admin navbar — passive badge only, no action link (Task 10)
- ✅ Cache invalidation on accept via try/except ImportError (Task 4)
- ✅ All tests from spec (Tasks 3–5 + 7)

**Type consistency:** `EventChangeRequest` fields used consistently across model → schema → routes. `ChangeRequestStatus` enum values (`pending`, `accepted`, `rejected`, `cancelled`) match across model, templates, and tests.

**Pending-count returns plain text:** The HTMX badge uses `hx-swap="innerHTML"` — the endpoint returns `PlainTextResponse(str(count))`. Returns empty string when count is 0 so the badge stays hidden (CSS `[&:not(:empty)]:flex`).
