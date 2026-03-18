# Recurring Appointment Series — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins and teachers to create recurring tutoring series (weekly / biweekly / custom N-week intervals, multiple day-slots with individual times) that pre-generate all `ScheduleEvent` rows, with context-menu UI to edit or delete from any occurrence forward.

**Architecture:** A new `recurring_series` table stores the recurrence rule. A pure-Python generation service (`app/services/series.py`) expands the rule into concrete `ScheduleEvent` rows on creation. The calendar JS gains a slide-in panel for series creation and a context menu for per-occurrence actions. `ScheduleEvent` gains a nullable `series_id` FK; the existing FullCalendar event load path is unchanged.

**Tech Stack:** FastAPI, SQLAlchemy async (mapped columns), Alembic, PostgreSQL JSONB, Pydantic v2, FullCalendar 6, Tailwind CSS, HTMX-compatible HTML fragments.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/models/series.py` | **Create** | `RecurringSeries` ORM model |
| `app/models/scheduling.py` | **Modify** | Add `series_id` FK + `series` relationship to `ScheduleEvent` |
| `app/models/__init__.py` | **Modify** | Export `RecurringSeries` |
| `app/db/base.py` | **Modify** | Import `RecurringSeries`, `UnavailableBlock`, `RescheduleProposal` for Alembic discovery |
| `app/schemas/series.py` | **Create** | `DaySlot`, `RecurringSeriesCreate`, `RecurringSeriesRead` |
| `app/schemas/scheduling.py` | **Modify** | Add `series_id: uuid.UUID | None` to `ScheduleEventRead` |
| `app/services/series.py` | **Create** | `generate_events()` pure-Python generation service |
| `app/api/routes_api.py` | **Modify** | Add series endpoints; harden `PATCH/DELETE /api/events/{id}` with auth |
| `alembic/versions/<hash>_add_recurring_series.py` | **Create** | Migration: `recurring_series` table + `series_id` FK on `schedule_events` |
| `app/templates/components/series_panel.html` | **Create** | Reusable slide-in panel fragment (shared by admin + teacher) |
| `app/templates/admin/calendar.html` | **Modify** | Include series panel; pass `is_admin=true` data attr |
| `app/templates/teacher/calendar.html` | **Modify** | Include series panel; extract inline JS to static file |
| `app/static/js/admin_calendar.js` | **Modify** | "New Series" button, panel wiring, context menu, series API calls |
| `app/static/js/teacher_calendar.js` | **Create** | Teacher-specific calendar init + series panel wiring (mirrors admin) |
| `app/static/js/series_panel.js` | **Create** | Shared panel logic: slot management, live preview count, form submission |
| `tests/test_series_generation.py` | **Create** | Unit tests for generation service (no DB needed) |
| `tests/test_series_api.py` | **Create** | Integration tests for series API endpoints |

---

## Task 1: `RecurringSeries` ORM Model

**Files:**
- Create: `app/models/series.py`
- Modify: `app/models/__init__.py`
- Modify: `app/db/base.py`

- [ ] **Step 1: Create `app/models/series.py`**

```python
"""RecurringSeries ORM model — stores recurrence rules for tutoring series."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent


class RecurringSeries(Base):
    """Recurrence rule for a set of tutoring sessions.

    Generates individual ScheduleEvent rows on creation.
    Stores the rule so 'edit from here' can re-generate forward events.
    """

    __tablename__ = "recurring_series"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    offering_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offerings.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    interval_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # day_slots: list of {day: 0-6, hour: 0-23, minute: 0-59, duration_minutes: int}
    day_slots: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    teacher: Mapped["User"] = relationship("User", foreign_keys=[teacher_id])
    student: Mapped["User | None"] = relationship("User", foreign_keys=[student_id])
    offering: Mapped["Offering"] = relationship("Offering")
    events: Mapped[list["ScheduleEvent"]] = relationship(
        "ScheduleEvent", back_populates="series", order_by="ScheduleEvent.start_time"
    )
```

- [ ] **Step 2: Update `app/models/__init__.py`**

Add to the existing imports and `__all__`:
```python
from app.models.series import RecurringSeries
```
And add `"RecurringSeries"` to `__all__`.

- [ ] **Step 3: Update `app/db/base.py`** (critical for Alembic autogenerate)

Replace the entire file:
```python
"""Import all models here so Alembic's autogenerate can discover them."""

from app.db.database import Base  # noqa: F401
from app.models.users import User  # noqa: F401
from app.models.offerings import Offering  # noqa: F401
from app.models.scheduling import ScheduleEvent  # noqa: F401
from app.models.availability import UnavailableBlock  # noqa: F401
from app.models.proposals import RescheduleProposal  # noqa: F401
from app.models.series import RecurringSeries  # noqa: F401
```

- [ ] **Step 4: Modify `app/models/scheduling.py`** — add `series_id` FK and `series` relationship

Add after the existing imports:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.series import RecurringSeries
```

Add to the `ScheduleEvent` class body (after `student_id`):
```python
series_id: Mapped[uuid.UUID | None] = mapped_column(
    ForeignKey("recurring_series.id", ondelete="SET NULL"), nullable=True
)

series: Mapped["RecurringSeries | None"] = relationship(
    "RecurringSeries", back_populates="events", foreign_keys=[series_id]
)
```

- [ ] **Step 5: Verify no circular import**

Run inside Docker:
```bash
docker-compose exec web python -c "from app.models.series import RecurringSeries; print('OK')"
```
Expected: `OK`

---

## Task 2: Alembic Migration

**Files:**
- Create: `alembic/versions/<hash>_add_recurring_series.py`

- [ ] **Step 1: Generate migration**

```bash
docker-compose exec web alembic revision --autogenerate -m "add_recurring_series"
```

Expected: New file created in `alembic/versions/`.

- [ ] **Step 2: Inspect the generated migration**

Open the generated file and verify it contains:
- `CREATE TABLE recurring_series` with columns: `id`, `teacher_id`, `student_id`, `offering_id`, `title`, `start_date`, `interval_weeks`, `day_slots` (JSONB), `end_date`, `end_count`, `created_at`
- `ALTER TABLE schedule_events ADD COLUMN series_id UUID REFERENCES recurring_series(id) ON DELETE SET NULL`

If autogenerate missed anything, add manually before applying.

- [ ] **Step 3: Apply migration**

```bash
docker-compose exec web alembic upgrade head
```

Expected: `Running upgrade ... -> <hash>, add_recurring_series` with no errors.

- [ ] **Step 4: Verify schema in PostgreSQL**

```bash
docker-compose exec db psql -U postgres -d ekorepetycje -c "\d recurring_series"
docker-compose exec db psql -U postgres -d ekorepetycje -c "\d schedule_events" | grep series_id
```

Expected: `recurring_series` table shown with all columns; `series_id` column present on `schedule_events`.

- [ ] **Step 5: Commit**

```bash
git add app/models/series.py app/models/scheduling.py app/models/__init__.py app/db/base.py alembic/versions/
git commit -m "feat(models): add RecurringSeries model and series_id FK on ScheduleEvent"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `app/schemas/series.py`
- Modify: `app/schemas/scheduling.py`

- [ ] **Step 1: Write failing test for schema validation**

Create `tests/test_series_schemas.py`:
```python
"""Tests for RecurringSeries Pydantic schemas."""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.series import RecurringSeriesCreate, DaySlot


def test_day_slot_valid():
    slot = DaySlot(day=0, hour=17, minute=0, duration_minutes=60)
    assert slot.day == 0
    assert slot.duration_minutes == 60


def test_day_slot_invalid_day():
    with pytest.raises(ValidationError):
        DaySlot(day=7, hour=17, minute=0, duration_minutes=60)


def test_series_create_requires_one_end_condition():
    """Exactly one of end_date/end_count must be set."""
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
            end_date=None,
            end_count=None,  # both None — invalid
        )


def test_series_create_both_end_conditions_invalid():
    """Both end_date and end_count set — invalid."""
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
            end_date=date(2026, 6, 30),
            end_count=10,  # both set — invalid
        )


def test_series_create_no_slots_invalid():
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[],  # empty — invalid
            end_count=10,
        )
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
docker-compose exec web pytest tests/test_series_schemas.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `app.schemas.series`.

- [ ] **Step 3: Create `app/schemas/series.py`**

```python
"""Pydantic schemas for RecurringSeries resources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, field_validator, model_validator
from pydantic import Field


class DaySlot(BaseModel):
    """One time slot within a recurring week."""

    day: Annotated[int, Field(ge=0, le=6)]  # 0=Monday, 6=Sunday
    hour: Annotated[int, Field(ge=0, le=23)]
    minute: Annotated[int, Field(ge=0, le=59)]
    duration_minutes: Annotated[int, Field(ge=15, le=480)]


class RecurringSeriesCreate(BaseModel):
    """Schema for creating a new recurring series."""

    teacher_id: uuid.UUID
    student_id: uuid.UUID | None = None
    offering_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    start_date: date
    interval_weeks: Annotated[int, Field(ge=1, le=52)]
    day_slots: Annotated[list[DaySlot], Field(min_length=1)]
    end_date: date | None = None
    end_count: Annotated[int | None, Field(ge=1, le=200)] = None

    @model_validator(mode="after")
    def exactly_one_end_condition(self) -> "RecurringSeriesCreate":
        """Exactly one of end_date or end_count must be provided."""
        has_date = self.end_date is not None
        has_count = self.end_count is not None
        if has_date == has_count:  # both or neither
            raise ValueError("Provide exactly one of end_date or end_count.")
        return self


class RecurringSeriesRead(BaseModel):
    """Schema returned when reading a recurring series."""

    id: uuid.UUID
    teacher_id: uuid.UUID
    student_id: uuid.UUID | None
    offering_id: uuid.UUID
    title: str
    start_date: date
    interval_weeks: int
    day_slots: list[DaySlot]
    end_date: date | None
    end_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update `app/schemas/scheduling.py`** — add `series_id` to `ScheduleEventRead`

In `ScheduleEventRead`, add:
```python
series_id: uuid.UUID | None = None
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
docker-compose exec web pytest tests/test_series_schemas.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas/series.py app/schemas/scheduling.py tests/test_series_schemas.py
git commit -m "feat(schemas): add DaySlot, RecurringSeriesCreate, RecurringSeriesRead; add series_id to ScheduleEventRead"
```

---

## Task 4: Generation Service

**Files:**
- Create: `app/services/series.py`
- Create: `tests/test_series_generation.py`

The generation service is pure Python (no DB). It takes a `RecurringSeriesCreate` payload + a series `id` and returns a list of `ScheduleEvent` ORM instances ready to `db.add_all()`. This makes it fully unit-testable.

- [ ] **Step 1: Write failing tests**

Create `tests/test_series_generation.py`:
```python
"""Unit tests for the series generation service."""
import uuid
from datetime import date, datetime, timezone, timedelta

import pytest

from app.schemas.series import RecurringSeriesCreate, DaySlot
from app.services.series import generate_events


OFFERING_ID = uuid.uuid4()
TEACHER_ID = uuid.uuid4()
SERIES_ID = uuid.uuid4()


def _base_payload(**kwargs) -> RecurringSeriesCreate:
    defaults = dict(
        teacher_id=TEACHER_ID,
        offering_id=OFFERING_ID,
        title="Matematyka",
        start_date=date(2026, 4, 6),  # Monday
        interval_weeks=1,
        day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
        end_count=4,
    )
    defaults.update(kwargs)
    return RecurringSeriesCreate(**defaults)


def test_weekly_by_count_generates_correct_count():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    assert len(events) == 4


def test_weekly_by_count_correct_days():
    """Events should all be on Monday (day=0)."""
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        assert ev.start_time.weekday() == 0  # Monday


def test_weekly_by_count_correct_time():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        assert ev.start_time.hour == 17
        assert ev.start_time.minute == 0


def test_weekly_by_count_correct_duration():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        delta = ev.end_time - ev.start_time
        assert delta == timedelta(minutes=60)


def test_weekly_interval_spacing():
    """Consecutive events should be exactly 7 days apart."""
    events = generate_events(_base_payload(end_count=3), SERIES_ID)
    gap = events[1].start_time - events[0].start_time
    assert gap == timedelta(weeks=1)


def test_biweekly_interval_spacing():
    events = generate_events(_base_payload(interval_weeks=2, end_count=3), SERIES_ID)
    gap = events[1].start_time - events[0].start_time
    assert gap == timedelta(weeks=2)


def test_weekly_by_end_date():
    """With end_date, stop before exceeding it."""
    payload = _base_payload(
        end_count=None,
        end_date=date(2026, 4, 27),  # 4 Mondays: Apr 6, 13, 20, 27
        day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
    )
    events = generate_events(payload, SERIES_ID)
    assert len(events) == 4
    # Last event is Apr 27
    assert events[-1].start_time.date() == date(2026, 4, 27)


def test_multi_slot_generates_multiple_events_per_week():
    """Two slots per week → 2 events per week iteration."""
    payload = _base_payload(
        end_count=6,
        day_slots=[
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),  # Monday
            DaySlot(day=3, hour=18, minute=30, duration_minutes=45),  # Thursday
        ],
    )
    events = generate_events(payload, SERIES_ID)
    assert len(events) == 6


def test_multi_slot_different_days():
    payload = _base_payload(
        end_count=4,
        day_slots=[
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),
            DaySlot(day=3, hour=18, minute=30, duration_minutes=45),
        ],
    )
    events = generate_events(payload, SERIES_ID)
    weekdays = [ev.start_time.weekday() for ev in events]
    assert 0 in weekdays  # Monday present
    assert 3 in weekdays  # Thursday present


def test_max_200_cap():
    """Generation raises ValueError if rule would generate more than 200 events."""
    payload = _base_payload(end_count=201)
    with pytest.raises(ValueError, match="200"):
        generate_events(payload, SERIES_ID)


def test_events_have_correct_series_id():
    events = generate_events(_base_payload(end_count=3), SERIES_ID)
    for ev in events:
        assert ev.series_id == SERIES_ID


def test_events_are_timezone_aware():
    events = generate_events(_base_payload(end_count=2), SERIES_ID)
    for ev in events:
        assert ev.start_time.tzinfo is not None
        assert ev.end_time.tzinfo is not None


def test_start_date_not_on_monday_anchors_to_week():
    """start_date on Wednesday → first Monday slot is that week's Monday."""
    payload = _base_payload(
        start_date=date(2026, 4, 8),  # Wednesday of week containing Mon Apr 6
        end_count=1,
        day_slots=[DaySlot(day=0, hour=10, minute=0, duration_minutes=60)],
    )
    events = generate_events(payload, SERIES_ID)
    assert events[0].start_time.date() == date(2026, 4, 6)  # Monday of same week


def test_events_sorted_by_start_time():
    """Multi-slot events should be sorted chronologically."""
    payload = _base_payload(
        end_count=4,
        day_slots=[
            DaySlot(day=3, hour=18, minute=0, duration_minutes=60),
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),
        ],
    )
    events = generate_events(payload, SERIES_ID)
    starts = [ev.start_time for ev in events]
    assert starts == sorted(starts)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
docker-compose exec web pytest tests/test_series_generation.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.series'`

- [ ] **Step 3: Create `app/services/series.py`**

```python
"""Series generation service.

Pure Python — no DB calls. Takes a RecurringSeriesCreate payload and a pre-assigned
series UUID, returns a list of ScheduleEvent ORM instances ready to db.add_all().
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.scheduling import ScheduleEvent
from app.schemas.series import RecurringSeriesCreate

_MAX_EVENTS = 200


def generate_events(
    payload: RecurringSeriesCreate,
    series_id: uuid.UUID,
) -> list[ScheduleEvent]:
    """Expand a recurrence rule into ScheduleEvent instances.

    Algorithm:
    - Find the Monday of the ISO week containing payload.start_date.
    - Walk forward week-by-week (step = payload.interval_weeks).
    - For each week, expand every day_slot into a (start, end) datetime pair.
    - Stop when end_count reached or the next slot would exceed end_date.
    - Sort results by start_time.
    - Raise ValueError if generation would exceed _MAX_EVENTS.
    """
    # Anchor to the Monday of start_date's ISO week
    sd = payload.start_date
    week_monday = sd - timedelta(days=sd.weekday())

    events: list[ScheduleEvent] = []
    week_offset = 0

    while True:
        current_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)

        for slot in payload.day_slots:
            slot_date = current_monday + timedelta(days=slot.day)
            slot_start = datetime(
                slot_date.year,
                slot_date.month,
                slot_date.day,
                slot.hour,
                slot.minute,
                tzinfo=timezone.utc,
            )
            slot_end = slot_start + timedelta(minutes=slot.duration_minutes)

            # end_date check: stop if this slot's date exceeds end_date
            if payload.end_date is not None and slot_date > payload.end_date:
                continue

            # end_count check: stop if we've already hit the limit
            if payload.end_count is not None and len(events) >= payload.end_count:
                break

            # Hard cap
            if len(events) >= _MAX_EVENTS:
                raise ValueError(
                    f"Series would generate more than {_MAX_EVENTS} events. "
                    "Reduce the duration or increase the interval."
                )

            events.append(
                ScheduleEvent(
                    title=payload.title,
                    start_time=slot_start,
                    end_time=slot_end,
                    offering_id=payload.offering_id,
                    teacher_id=payload.teacher_id,
                    student_id=payload.student_id,
                    series_id=series_id,
                )
            )

        week_offset += 1

        # Termination: by count
        if payload.end_count is not None and len(events) >= payload.end_count:
            break

        # Termination: by date — stop when Monday of current week exceeds end_date
        if payload.end_date is not None:
            next_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)
            # All slots in the next week would have dates >= next_monday
            # If next_monday > end_date, no more slots can be before end_date
            if next_monday > payload.end_date:
                break

    events.sort(key=lambda e: e.start_time)
    return events
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
docker-compose exec web pytest tests/test_series_generation.py -v
```

Expected: All 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/series.py tests/test_series_generation.py
git commit -m "feat(services): add series generation service with full unit test coverage"
```

---

## Task 5: API Endpoints

**Files:**
- Modify: `app/api/routes_api.py`
- Create: `tests/test_series_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_series_api.py`:
```python
"""Integration tests for recurring series API endpoints."""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_create_series_unauthenticated(client):
    """Unauthenticated request must be redirected to login."""
    resp = await client.post("/api/series", json={})
    assert resp.status_code in (303, 401, 422)


async def test_patch_event_unauthenticated(client):
    """PATCH /api/events/{id} must require auth after hardening."""
    resp = await client.patch(f"/api/events/{uuid.uuid4()}", json={})
    # Should not be 200/404 — must redirect or 401
    assert resp.status_code in (303, 401, 403, 422)


async def test_delete_event_unauthenticated(client):
    """DELETE /api/events/{id} must require auth after hardening."""
    resp = await client.delete(f"/api/events/{uuid.uuid4()}")
    assert resp.status_code in (303, 401, 403)
```

- [ ] **Step 2: Run tests**

```bash
docker-compose exec web pytest tests/test_series_api.py -v
```

`test_patch_event_unauthenticated` and `test_delete_event_unauthenticated` should **FAIL** (currently return 404, not 303/401) — confirming the security gap.

- [ ] **Step 3: Add series imports to `routes_api.py`**

At the top of `app/api/routes_api.py`, add:
```python
from app.models.series import RecurringSeries
from app.schemas.series import RecurringSeriesCreate, RecurringSeriesRead
from app.services.series import generate_events
from app.core.auth import get_current_user, require_admin, require_teacher_or_admin
from fastapi import Request
```

Also add `from sqlalchemy.orm import selectinload` to imports.

- [ ] **Step 4: Harden existing event endpoints**

Replace the existing `update_event` and `delete_event` functions:

```python
@router.patch("/events/{event_id}", response_model=ScheduleEventRead)
async def update_event(
    event_id: UUID,
    payload: ScheduleEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> ScheduleEventRead:
    """Update a single schedule event. Teachers can only update their own events."""
    result = await db.execute(select(ScheduleEvent).where(ScheduleEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if current_user.role != UserRole.ADMIN and event.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your event")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.flush()
    await db.refresh(event)
    return ScheduleEventRead.model_validate(event)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> None:
    """Delete a single schedule event. Teachers can only delete their own events."""
    result = await db.execute(select(ScheduleEvent).where(ScheduleEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if current_user.role != UserRole.ADMIN and event.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your event")
    await db.delete(event)
    await db.flush()
```

- [ ] **Step 5: Add series endpoints**

Append to `app/api/routes_api.py`:

```python
# ─── Recurring Series ─────────────────────────────────────────────────────────

@router.post("/series", status_code=201)
async def create_series(
    payload: RecurringSeriesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Create a recurring series and pre-generate all ScheduleEvent rows."""
    # Ownership check: teachers can only create series for themselves.
    if current_user.role != UserRole.ADMIN and payload.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot create series for another teacher")

    series_id = uuid.uuid4()

    # Generate events (raises ValueError if > 200)
    try:
        events = generate_events(payload, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    series = RecurringSeries(
        id=series_id,
        teacher_id=payload.teacher_id,
        student_id=payload.student_id,
        offering_id=payload.offering_id,
        title=payload.title,
        start_date=payload.start_date,
        interval_weeks=payload.interval_weeks,
        day_slots=[s.model_dump() for s in payload.day_slots],
        end_date=payload.end_date,
        end_count=payload.end_count,
    )
    db.add(series)
    db.add_all(events)
    await db.flush()

    return {"series_id": str(series_id), "events_created": len(events)}


@router.get("/series/{series_id}", response_model=RecurringSeriesRead)
async def get_series(
    series_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> RecurringSeriesRead:
    """Return series rule for pre-filling the edit panel."""
    result = await db.execute(
        select(RecurringSeries).where(RecurringSeries.id == series_id)
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")
    return RecurringSeriesRead.model_validate(series)


@router.delete("/series/{series_id}/from/{event_id}", status_code=204)
async def delete_series_from(
    series_id: UUID,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> None:
    """Delete an event and all following events in the series."""
    series_result = await db.execute(
        select(RecurringSeries).where(RecurringSeries.id == series_id)
    )
    series = series_result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")

    # Find the pivot event to get its start_time
    pivot_result = await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == event_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot:
        raise HTTPException(status_code=404, detail="Event not found")

    # Delete this event and all future events in the series
    future_result = await db.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.series_id == series_id,
            ScheduleEvent.start_time >= pivot.start_time,
        )
    )
    for event in future_result.scalars().all():
        await db.delete(event)

    # If no events remain in the series, delete the series record too
    remaining_result = await db.execute(
        select(func.count(ScheduleEvent.id)).where(ScheduleEvent.series_id == series_id)
    )
    if remaining_result.scalar_one() == 0:
        await db.delete(series)

    await db.flush()


@router.patch("/series/{series_id}/from/{event_id}", status_code=200)
async def update_series_from(
    series_id: UUID,
    event_id: UUID,
    payload: RecurringSeriesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Delete event and all following, re-generate from updated rule starting that ISO week."""
    series_result = await db.execute(
        select(RecurringSeries).where(RecurringSeries.id == series_id)
    )
    series = series_result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")

    pivot_result = await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == event_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot:
        raise HTTPException(status_code=404, detail="Event not found")

    # Compute ISO-week anchor: Monday of pivot's week
    pivot_date = pivot.start_time.date()
    week_monday = pivot_date - __import__("datetime").timedelta(days=pivot_date.weekday())

    # Delete pivot and all future events in the series
    future_result = await db.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.series_id == series_id,
            ScheduleEvent.start_time >= pivot.start_time,
        )
    )
    for event in future_result.scalars().all():
        await db.delete(event)
    await db.flush()

    # Re-generate from the ISO week anchor using updated rule
    regenerate_payload = payload.model_copy(update={"start_date": week_monday})
    try:
        new_events = generate_events(regenerate_payload, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Update the series rule record
    series.title = payload.title
    series.interval_weeks = payload.interval_weeks
    series.day_slots = [s.model_dump() for s in payload.day_slots]
    series.end_date = payload.end_date
    series.end_count = payload.end_count

    db.add_all(new_events)
    await db.flush()

    return {"series_id": str(series_id), "events_updated": len(new_events)}
```

- [ ] **Step 6: Add `uuid` import to routes_api.py top-level if missing**

Verify `import uuid` is at the top of `routes_api.py`. Add if not present.

- [ ] **Step 7: Run full test suite**

```bash
docker-compose exec web pytest tests/ -v
```

Expected: All tests PASS including `test_series_api.py` auth tests.

- [ ] **Step 8: Commit**

```bash
git add app/api/routes_api.py tests/test_series_api.py
git commit -m "feat(api): add series endpoints; harden PATCH/DELETE events with auth"
```

---

## Task 6: Admin Calendar UI

**Files:**
- Create: `app/templates/components/series_panel.html`
- Create: `app/static/js/series_panel.js`
- Modify: `app/static/js/admin_calendar.js`
- Modify: `app/templates/admin/calendar.html`

The series panel is a slide-in drawer rendered from the right. It is shared by admin and teacher calendars. `data-is-admin` attribute controls whether the teacher dropdown is shown.

- [ ] **Step 1: Create `app/templates/components/series_panel.html`**

```html
<!-- Recurring Series Slide-in Panel -->
<!-- Usage: include with is_admin=true|false, user_id="uuid" -->
<div id="series-panel"
     class="fixed inset-y-0 right-0 w-full sm:w-[480px] bg-gray-950 border-l border-gray-800 shadow-2xl transform translate-x-full transition-transform duration-300 ease-in-out z-50 flex flex-col"
     data-is-admin="{{ 'true' if is_admin else 'false' }}"
     data-user-id="{{ user.id }}">

    <!-- Panel Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-gray-800">
        <h2 class="text-lg font-semibold text-white" id="series-panel-title">Nowa seria zajęć</h2>
        <button onclick="closeSeriesPanel()" class="text-gray-400 hover:text-white transition-colors">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
        </button>
    </div>

    <!-- Panel Body (scrollable) -->
    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-5">

        <!-- Teacher (admin only) -->
        <div id="teacher-field" class="hidden">
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Nauczyciel</label>
            <select id="sp-teacher" class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500">
                <option value="">Wybierz nauczyciela...</option>
            </select>
        </div>

        <!-- Student -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Uczeń (opcjonalnie)</label>
            <select id="sp-student" class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500">
                <option value="">Brak / przypisz później</option>
            </select>
        </div>

        <!-- Offering -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Oferta</label>
            <select id="sp-offering" onchange="spAutoFillTitle()" class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500">
                <option value="">Wybierz ofertę...</option>
            </select>
        </div>

        <!-- Title -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Tytuł zajęć</label>
            <input type="text" id="sp-title" maxlength="255"
                   class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500"
                   placeholder="np. Matematyka — przygotowanie do matury">
        </div>

        <!-- Start date -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Pierwsza lekcja (tydzień startowy)</label>
            <input type="date" id="sp-start-date"
                   class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500">
        </div>

        <!-- Interval -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-1.5 uppercase tracking-wide">Częstotliwość</label>
            <div class="flex gap-2">
                <button type="button" onclick="spSetInterval(1)" data-interval="1"
                        class="sp-interval-btn flex-1 py-2 rounded-xl text-sm font-medium border border-gray-700 text-gray-300 hover:border-green-500 hover:text-green-400 transition-colors">
                    Co tydzień
                </button>
                <button type="button" onclick="spSetInterval(2)" data-interval="2"
                        class="sp-interval-btn flex-1 py-2 rounded-xl text-sm font-medium border border-gray-700 text-gray-300 hover:border-green-500 hover:text-green-400 transition-colors">
                    Co 2 tygodnie
                </button>
                <button type="button" onclick="spSetInterval(0)" data-interval="0"
                        class="sp-interval-btn flex-1 py-2 rounded-xl text-sm font-medium border border-gray-700 text-gray-300 hover:border-green-500 hover:text-green-400 transition-colors">
                    Własny
                </button>
            </div>
            <div id="sp-custom-interval" class="hidden mt-2">
                <input type="number" id="sp-interval-value" min="1" max="52" value="3"
                       class="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-green-500"
                       placeholder="Co ile tygodni?">
            </div>
        </div>

        <!-- Day Slots -->
        <div>
            <div class="flex items-center justify-between mb-2">
                <label class="text-xs font-medium text-gray-400 uppercase tracking-wide">Godziny zajęć</label>
                <button type="button" onclick="spAddSlot()"
                        class="text-xs text-green-400 hover:text-green-300 transition-colors">+ Dodaj slot</button>
            </div>
            <div id="sp-slots" class="space-y-2"></div>
        </div>

        <!-- End Condition -->
        <div>
            <label class="block text-xs font-medium text-gray-400 mb-2 uppercase tracking-wide">Zakończenie serii</label>
            <div class="space-y-2">
                <label class="flex items-center gap-3 cursor-pointer">
                    <input type="radio" name="sp-end-type" value="count" checked onchange="spToggleEnd()"
                           class="text-green-500 focus:ring-green-500">
                    <span class="text-sm text-gray-300">Liczba zajęć</span>
                    <input type="number" id="sp-end-count" min="1" max="200" value="10"
                           class="ml-auto w-20 bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none">
                </label>
                <label class="flex items-center gap-3 cursor-pointer">
                    <input type="radio" name="sp-end-type" value="date" onchange="spToggleEnd()"
                           class="text-green-500 focus:ring-green-500">
                    <span class="text-sm text-gray-300">Data końcowa</span>
                    <input type="date" id="sp-end-date" disabled
                           class="ml-auto bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none disabled:opacity-40">
                </label>
            </div>
        </div>

        <!-- Preview -->
        <div class="bg-gray-900/60 border border-gray-800 rounded-xl px-4 py-3">
            <p class="text-xs text-gray-400">Zostanie utworzonych: <span id="sp-preview-count" class="text-white font-semibold">—</span> zajęć</p>
        </div>

        <!-- Error -->
        <div id="sp-error" class="hidden bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3">
            <p class="text-sm text-red-400" id="sp-error-text"></p>
        </div>
    </div>

    <!-- Panel Footer -->
    <div class="px-6 py-4 border-t border-gray-800">
        <button onclick="spSubmit()"
                class="w-full bg-green-500 hover:bg-green-400 text-gray-950 font-semibold py-2.5 rounded-xl text-sm transition-colors">
            Utwórz serię
        </button>
    </div>
</div>

<!-- Panel backdrop -->
<div id="series-backdrop"
     onclick="closeSeriesPanel()"
     class="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 hidden">
</div>
```

- [ ] **Step 2: Create `app/static/js/series_panel.js`**

```javascript
/**
 * Shared series panel logic — used by both admin and teacher calendars.
 *
 * Depends on:
 *   - #series-panel element (from series_panel.html component)
 *   - window._calendar  (FullCalendar instance, set by calendar init code)
 *   - window._seriesPanelMode: 'create' | 'edit'
 *   - window._editSeriesId, window._editFromEventId (for edit mode)
 */

const DAY_NAMES = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'];
let _currentIntervalWeeks = 1;
let _offerings = [];
let _teachers = [];
let _students = [];

// ─── Panel open/close ──────────────────────────────────────────────────────

function openSeriesPanel() {
    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.remove('translate-x-full');
    backdrop.classList.remove('hidden');
    document.getElementById('series-panel-title').textContent = 'Nowa seria zajęć';
    window._seriesPanelMode = 'create';
    _spInitDropdowns();
    spAddSlot(); // add one default slot
    spUpdatePreview();
}

function openSeriesPanelEdit(seriesId, fromEventId) {
    window._seriesPanelMode = 'edit';
    window._editSeriesId = seriesId;
    window._editFromEventId = fromEventId;

    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.remove('translate-x-full');
    backdrop.classList.remove('hidden');
    document.getElementById('series-panel-title').textContent = 'Edytuj serię od tej lekcji';

    // Load existing series data and pre-fill
    fetch(`/api/series/${seriesId}`)
        .then(r => r.json())
        .then(data => {
            _spInitDropdowns(data);
        });
}

function closeSeriesPanel() {
    const panel = document.getElementById('series-panel');
    const backdrop = document.getElementById('series-backdrop');
    panel.classList.add('translate-x-full');
    backdrop.classList.add('hidden');
    // Clear slots
    document.getElementById('sp-slots').innerHTML = '';
    document.getElementById('sp-error').classList.add('hidden');
}

// ─── Dropdown population ────────────────────────────────────────────────────

async function _spInitDropdowns(prefill = null) {
    const panel = document.getElementById('series-panel');
    const isAdmin = panel.dataset.isAdmin === 'true';
    const userId = panel.dataset.userId;

    // Teachers (admin only)
    if (isAdmin) {
        document.getElementById('teacher-field').classList.remove('hidden');
        if (_teachers.length === 0) {
            const res = await fetch('/api/teachers');
            _teachers = await res.json();
        }
        const sel = document.getElementById('sp-teacher');
        sel.innerHTML = '<option value="">Wybierz nauczyciela...</option>' +
            _teachers.map(t => `<option value="${t.id}">${t.full_name}</option>`).join('');
        if (prefill) sel.value = prefill.teacher_id;
    }

    // Students
    if (_students.length === 0) {
        const res = await fetch('/api/students');
        _students = await res.json();
    }
    const stuSel = document.getElementById('sp-student');
    stuSel.innerHTML = '<option value="">Brak / przypisz później</option>' +
        _students.map(s => `<option value="${s.id}">${s.full_name}</option>`).join('');
    if (prefill && prefill.student_id) stuSel.value = prefill.student_id;

    // Offerings
    if (_offerings.length === 0) {
        const res = await fetch('/api/offerings');
        _offerings = await res.json();
    }
    const offSel = document.getElementById('sp-offering');
    offSel.innerHTML = '<option value="">Wybierz ofertę...</option>' +
        _offerings.map(o => `<option value="${o.id}">${o.title}</option>`).join('');
    if (prefill) {
        offSel.value = prefill.offering_id;
        document.getElementById('sp-title').value = prefill.title;
        document.getElementById('sp-start-date').value = prefill.start_date;
        spSetInterval(prefill.interval_weeks);

        // Slots
        document.getElementById('sp-slots').innerHTML = '';
        prefill.day_slots.forEach(slot => spAddSlot(slot));

        // End condition
        if (prefill.end_count) {
            document.querySelector('input[name="sp-end-type"][value="count"]').checked = true;
            document.getElementById('sp-end-count').value = prefill.end_count;
            spToggleEnd();
        } else if (prefill.end_date) {
            document.querySelector('input[name="sp-end-type"][value="date"]').checked = true;
            document.getElementById('sp-end-date').value = prefill.end_date;
            spToggleEnd();
        }
    }
    spUpdatePreview();
}

// ─── Interval selector ──────────────────────────────────────────────────────

function spSetInterval(weeks) {
    _currentIntervalWeeks = weeks;
    document.querySelectorAll('.sp-interval-btn').forEach(btn => {
        const active = parseInt(btn.dataset.interval) === weeks ||
            (btn.dataset.interval === '0' && weeks > 2);
        btn.classList.toggle('border-green-500', active);
        btn.classList.toggle('text-green-400', active);
        btn.classList.toggle('border-gray-700', !active);
        btn.classList.toggle('text-gray-300', !active);
    });
    const custom = document.getElementById('sp-custom-interval');
    if (weeks === 0 || weeks > 2) {
        custom.classList.remove('hidden');
        if (weeks > 2) document.getElementById('sp-interval-value').value = weeks;
    } else {
        custom.classList.add('hidden');
    }
    spUpdatePreview();
}

// ─── Day slots ──────────────────────────────────────────────────────────────

function spAddSlot(prefill = null) {
    const container = document.getElementById('sp-slots');
    const idx = container.children.length;
    const slot = document.createElement('div');
    slot.className = 'flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-3 py-2';
    slot.innerHTML = `
        <select class="sp-slot-day bg-transparent text-white text-sm focus:outline-none" onchange="spUpdatePreview()">
            ${DAY_NAMES.map((n, i) => `<option value="${i}"${prefill && prefill.day === i ? ' selected' : ''}>${n}</option>`).join('')}
        </select>
        <input type="time" class="sp-slot-time bg-transparent text-white text-sm focus:outline-none w-24"
               value="${prefill ? String(prefill.hour).padStart(2,'0') + ':' + String(prefill.minute).padStart(2,'0') : '17:00'}"
               onchange="spUpdatePreview()">
        <input type="number" class="sp-slot-duration bg-gray-800 border border-gray-700 text-white text-sm px-2 py-1 rounded-lg w-20 focus:outline-none"
               value="${prefill ? prefill.duration_minutes : 60}" min="15" max="480" placeholder="min"
               onchange="spUpdatePreview()">
        <span class="text-xs text-gray-500">min</span>
        <button type="button" onclick="this.parentElement.remove(); spUpdatePreview()"
                class="ml-auto text-gray-600 hover:text-red-400 transition-colors text-lg leading-none">×</button>
    `;
    container.appendChild(slot);
    spUpdatePreview();
}

// ─── End condition toggle ────────────────────────────────────────────────────

function spToggleEnd() {
    const type = document.querySelector('input[name="sp-end-type"]:checked').value;
    document.getElementById('sp-end-count').disabled = type !== 'count';
    document.getElementById('sp-end-date').disabled = type !== 'date';
    spUpdatePreview();
}

// ─── Live preview ────────────────────────────────────────────────────────────

function spUpdatePreview() {
    const slots = document.querySelectorAll('#sp-slots > div').length;
    if (slots === 0) {
        document.getElementById('sp-preview-count').textContent = '—';
        return;
    }

    const endType = document.querySelector('input[name="sp-end-type"]:checked')?.value;
    let count = '—';

    if (endType === 'count') {
        const n = parseInt(document.getElementById('sp-end-count').value) || 0;
        count = n; // slots * weeks is handled server-side; count = total events
    } else if (endType === 'date') {
        const startVal = document.getElementById('sp-start-date').value;
        const endVal = document.getElementById('sp-end-date').value;
        const weeks = _getIntervalWeeks();
        if (startVal && endVal && weeks > 0) {
            const start = new Date(startVal);
            const end = new Date(endVal);
            const diffMs = end - start;
            if (diffMs >= 0) {
                const diffWeeks = Math.floor(diffMs / (7 * 24 * 3600 * 1000));
                const iterations = Math.floor(diffWeeks / weeks) + 1;
                count = iterations * slots;
            }
        }
    }
    document.getElementById('sp-preview-count').textContent = count;
}

function _getIntervalWeeks() {
    if (_currentIntervalWeeks > 0 && _currentIntervalWeeks <= 2) return _currentIntervalWeeks;
    return parseInt(document.getElementById('sp-interval-value')?.value) || 1;
}

// ─── Auto-fill title from offering ──────────────────────────────────────────

function spAutoFillTitle() {
    const offId = document.getElementById('sp-offering').value;
    const off = _offerings.find(o => o.id === offId);
    if (off) document.getElementById('sp-title').value = off.title;
}

// ─── Build payload ───────────────────────────────────────────────────────────

function _buildPayload() {
    const panel = document.getElementById('series-panel');
    const isAdmin = panel.dataset.isAdmin === 'true';
    const userId = panel.dataset.userId;

    const teacherId = isAdmin
        ? document.getElementById('sp-teacher').value
        : userId;
    const studentId = document.getElementById('sp-student').value || null;
    const offeringId = document.getElementById('sp-offering').value;
    const title = document.getElementById('sp-title').value.trim();
    const startDate = document.getElementById('sp-start-date').value;
    const intervalWeeks = _getIntervalWeeks();

    const slots = Array.from(document.querySelectorAll('#sp-slots > div')).map(row => {
        const [h, m] = row.querySelector('.sp-slot-time').value.split(':').map(Number);
        return {
            day: parseInt(row.querySelector('.sp-slot-day').value),
            hour: h,
            minute: m,
            duration_minutes: parseInt(row.querySelector('.sp-slot-duration').value),
        };
    });

    const endType = document.querySelector('input[name="sp-end-type"]:checked').value;
    const endCount = endType === 'count' ? parseInt(document.getElementById('sp-end-count').value) : null;
    const endDate = endType === 'date' ? document.getElementById('sp-end-date').value : null;

    return { teacher_id: teacherId, student_id: studentId, offering_id: offeringId,
             title, start_date: startDate, interval_weeks: intervalWeeks,
             day_slots: slots, end_date: endDate, end_count: endCount };
}

// ─── Submit ──────────────────────────────────────────────────────────────────

async function spSubmit() {
    const payload = _buildPayload();
    const errEl = document.getElementById('sp-error');
    const errText = document.getElementById('sp-error-text');
    errEl.classList.add('hidden');

    let url = '/api/series';
    let method = 'POST';

    if (window._seriesPanelMode === 'edit') {
        url = `/api/series/${window._editSeriesId}/from/${window._editFromEventId}`;
        method = 'PATCH';
    }

    try {
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (resp.ok) {
            closeSeriesPanel();
            if (window._calendar) window._calendar.refetchEvents();
        } else {
            const data = await resp.json();
            errText.textContent = data.detail || 'Błąd podczas zapisywania serii.';
            errEl.classList.remove('hidden');
        }
    } catch (err) {
        errText.textContent = 'Błąd sieci. Sprawdź połączenie.';
        errEl.classList.remove('hidden');
    }
}
```

- [ ] **Step 3: Add `GET /api/students` endpoint to `routes_api.py`**

The series panel needs a students dropdown. Add:
```python
@router.get("/students", response_model=list[dict])
async def get_students(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return all students for dropdown population."""
    result = await db.execute(select(User).where(User.role == UserRole.STUDENT))
    return [{"id": str(u.id), "full_name": u.full_name} for u in result.scalars().all()]
```

- [ ] **Step 4: Update `app/static/js/admin_calendar.js`**

Replace the entire file:

```javascript
/**
 * FullCalendar initialization for the Ekorepetycje admin panel.
 * Fetches events from GET /api/events and handles CRUD + series context menu.
 */
document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        locale: 'pl',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'newSeries dayGridMonth,timeGridWeek,timeGridDay',
        },
        customButtons: {
            newSeries: {
                text: '+ Nowa seria',
                click: function () { openSeriesPanel(); },
            },
        },
        height: 'auto',
        slotMinTime: '07:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false,
        nowIndicator: true,
        editable: true,
        selectable: true,
        eventColor: '#22c55e',
        eventTextColor: '#030712',

        events: {
            url: '/api/events',
            method: 'GET',
            failure: function () { console.error('Failed to load events'); },
        },

        eventDataTransform: function (rawEvent) {
            return {
                id: rawEvent.id,
                title: rawEvent.title,
                start: rawEvent.start_time,
                end: rawEvent.end_time,
                extendedProps: {
                    status: rawEvent.status,
                    offering_id: rawEvent.offering_id,
                    teacher_id: rawEvent.teacher_id,
                    student_id: rawEvent.student_id,
                    series_id: rawEvent.series_id,
                },
                color: rawEvent.status === 'completed' ? '#4b5563' :
                       rawEvent.status === 'cancelled' ? '#ef4444' : '#22c55e',
            };
        },

        eventDrop: async function (info) {
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        eventResize: async function (info) {
            const ok = await _patchEvent(info.event);
            if (!ok) info.revert();
        },

        eventClick: function (info) {
            _showContextMenu(info.event, info.jsEvent);
        },

        select: function () { calendar.unselect(); },
    });

    calendar.render();
    window._calendar = calendar;
});

// ─── PATCH single event (drag/resize) ───────────────────────────────────────

async function _patchEvent(event) {
    try {
        const resp = await fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: event.title,
                start_time: event.start.toISOString(),
                end_time: event.end.toISOString(),
                offering_id: event.extendedProps.offering_id,
                teacher_id: event.extendedProps.teacher_id,
                student_id: event.extendedProps.student_id,
                status: event.extendedProps.status,
            }),
        });
        return resp.ok;
    } catch { return false; }
}

// ─── Context menu ────────────────────────────────────────────────────────────

let _activeMenu = null;

function _showContextMenu(event, jsEvent) {
    _closeContextMenu();

    const seriesId = event.extendedProps.series_id;
    const isSeries = !!seriesId;

    const menu = document.createElement('div');
    menu.id = 'fc-context-menu';
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[220px] text-sm';
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    const items = [];

    if (isSeries) {
        items.push({
            label: 'Edytuj tę lekcję',
            action: () => _editSingleEvent(event),
        });
        items.push({
            label: 'Edytuj tę i następne',
            action: () => openSeriesPanelEdit(seriesId, event.id),
        });
        items.push({ divider: true });
        items.push({
            label: 'Usuń tę lekcję',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const resp = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (resp.ok) event.remove();
            },
        });
        items.push({
            label: 'Usuń tę i następne',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń tę i wszystkie następne lekcje z serii "${event.title}"?`)) return;
                const resp = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE' });
                if (resp.ok && window._calendar) window._calendar.refetchEvents();
            },
        });
    } else {
        items.push({
            label: 'Edytuj',
            action: () => _editSingleEvent(event),
        });
        items.push({ divider: true });
        items.push({
            label: 'Usuń',
            danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const resp = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (resp.ok) event.remove();
            },
        });
    }

    items.forEach(item => {
        if (item.divider) {
            const hr = document.createElement('div');
            hr.className = 'border-t border-gray-800 my-1';
            menu.appendChild(hr);
            return;
        }
        const btn = document.createElement('button');
        btn.className = `w-full text-left px-4 py-2 transition-colors ${
            item.danger
                ? 'text-red-400 hover:bg-red-500/10'
                : 'text-gray-200 hover:bg-gray-800'
        }`;
        btn.textContent = item.label;
        btn.onclick = () => { _closeContextMenu(); item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeMenu = menu;

    // Adjust position if off-screen
    requestAnimationFrame(() => {
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            menu.style.left = (jsEvent.pageX - rect.width) + 'px';
        }
        if (rect.bottom > window.innerHeight) {
            menu.style.top = (jsEvent.pageY - rect.height) + 'px';
        }
    });

    setTimeout(() => document.addEventListener('click', _closeContextMenu, { once: true }), 0);
}

function _closeContextMenu() {
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
}

function _editSingleEvent(event) {
    // Simple prompt-based inline edit for title (full modal is future work)
    const newTitle = prompt('Tytuł zajęć:', event.title);
    if (newTitle && newTitle.trim()) {
        fetch(`/api/events/${event.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: newTitle.trim(),
                start_time: event.start.toISOString(),
                end_time: event.end.toISOString(),
                offering_id: event.extendedProps.offering_id,
                teacher_id: event.extendedProps.teacher_id,
                student_id: event.extendedProps.student_id,
                status: event.extendedProps.status,
            }),
        }).then(r => { if (r.ok) event.setProp('title', newTitle.trim()); });
    }
}
```

- [ ] **Step 5: Update `app/templates/admin/calendar.html`**

Replace the file:
```html
{% extends "base.html" %}

{% block navbar %}{% include "components/navbar_admin.html" %}{% endblock %}

{% block title %}Kalendarz — Ekorepetycje Admin{% endblock %}

{% block extra_head %}
<link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.css" rel="stylesheet">
{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-6 max-w-7xl mx-auto">
    <div class="mb-8 flex items-center justify-between">
        <div>
            <h1 class="text-3xl font-bold text-white">Kalendarz Zajęć</h1>
            <p class="text-gray-400 mt-1">Przeciągnij i upuść, aby przełożyć zajęcia</p>
        </div>
        <a href="/admin/" class="text-sm text-gray-400 hover:text-white transition-colors flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
            </svg>
            Dashboard
        </a>
    </div>

    <div class="bg-gray-900/50 border border-gray-800/50 rounded-2xl p-6">
        <div id="calendar" class="fc-dark"></div>
    </div>
</div>

{% set is_admin = true %}
{% include "components/series_panel.html" %}
{% endblock %}

{% block extra_scripts %}
<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js"></script>
<script src="/static/js/series_panel.js"></script>
<script src="/static/js/admin_calendar.js"></script>

<style>
.fc { color: #f3f4f6; }
.fc-theme-standard .fc-scrollgrid { border-color: #1f2937; }
.fc-theme-standard td, .fc-theme-standard th { border-color: #1f2937; }
.fc .fc-col-header-cell-cushion { color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
.fc .fc-daygrid-day-number { color: #6b7280; font-size: 0.875rem; }
.fc .fc-timegrid-slot-label { color: #4b5563; font-size: 0.75rem; }
.fc .fc-toolbar-title { color: #f9fafb; font-size: 1.125rem; font-weight: 600; }
.fc .fc-button { background-color: #1f2937; border-color: #374151; color: #d1d5db; font-size: 0.875rem; padding: 0.375rem 0.75rem; }
.fc .fc-button:hover { background-color: #374151; }
.fc .fc-button-primary:not(:disabled).fc-button-active { background-color: #22c55e; border-color: #22c55e; color: #030712; }
.fc-button.fc-newSeries-button { background-color: #22c55e !important; border-color: #22c55e !important; color: #030712 !important; font-weight: 600; }
.fc-button.fc-newSeries-button:hover { background-color: #16a34a !important; }
.fc .fc-now-indicator-line { border-color: #22c55e; }
.fc .fc-highlight { background: rgba(34, 197, 94, 0.1); }
.fc .fc-timegrid-now-indicator-arrow { border-top-color: #22c55e; border-bottom-color: #22c55e; }
</style>
{% endblock %}
```

- [ ] **Step 6: Commit**

```bash
git add app/templates/components/series_panel.html app/static/js/series_panel.js app/static/js/admin_calendar.js app/templates/admin/calendar.html app/api/routes_api.py
git commit -m "feat(ui): admin calendar series panel, context menu, hardened event endpoints"
```

---

## Task 7: Teacher Calendar UI

**Files:**
- Create: `app/static/js/teacher_calendar.js`
- Modify: `app/templates/teacher/calendar.html`

- [ ] **Step 1: Create `app/static/js/teacher_calendar.js`**

```javascript
/**
 * FullCalendar initialization for the teacher calendar view.
 * Teacher ID is injected from the template as window.TEACHER_ID.
 */
document.addEventListener('DOMContentLoaded', function () {
    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) return;

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'newSeries dayGridMonth,timeGridWeek,timeGridDay',
        },
        customButtons: {
            newSeries: {
                text: '+ Nowa seria',
                click: function () { openSeriesPanel(); },
            },
        },
        locale: 'pl',
        height: 'auto',
        slotMinTime: '07:00:00',
        slotMaxTime: '22:00:00',
        allDaySlot: false,
        nowIndicator: true,
        editable: false,  // teachers don't drag-drop; they use proposals
        selectable: false,

        eventSources: [
            {
                url: `/api/events?teacher_id=${window.TEACHER_ID}`,
                failure: function () { console.error('Failed to load events'); },
            },
            {
                url: `/api/availability/${window.TEACHER_ID}`,
                display: 'background',
                color: '#6b7280',
            },
        ],

        eventDataTransform: function (rawEvent) {
            return {
                id: rawEvent.id,
                title: rawEvent.title,
                start: rawEvent.start_time,
                end: rawEvent.end_time,
                extendedProps: {
                    status: rawEvent.status,
                    offering_id: rawEvent.offering_id,
                    teacher_id: rawEvent.teacher_id,
                    student_id: rawEvent.student_id,
                    series_id: rawEvent.series_id,
                },
                color: rawEvent.status === 'completed' ? '#4b5563' :
                       rawEvent.status === 'cancelled' ? '#ef4444' : '#22c55e',
                textColor: '#030712',
            };
        },

        eventClick: function (info) {
            _showTeacherContextMenu(info.event, info.jsEvent);
        },
    });

    calendar.render();
    window._calendar = calendar;
});

// ─── Context menu (teacher-scoped) ───────────────────────────────────────────

let _activeMenu = null;

function _showTeacherContextMenu(event, jsEvent) {
    if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }

    const seriesId = event.extendedProps.series_id;
    const menu = document.createElement('div');
    menu.className = 'fixed z-50 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl py-1 min-w-[220px] text-sm';
    menu.style.left = jsEvent.pageX + 'px';
    menu.style.top = jsEvent.pageY + 'px';

    const items = seriesId ? [
        { label: 'Edytuj tę i następne', action: () => openSeriesPanelEdit(seriesId, event.id) },
        { divider: true },
        {
            label: 'Usuń tę lekcję', danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (r.ok) event.remove();
            },
        },
        {
            label: 'Usuń tę i następne', danger: true,
            action: async () => {
                if (!confirm('Usuń tę i wszystkie następne lekcje z serii?')) return;
                const r = await fetch(`/api/series/${seriesId}/from/${event.id}`, { method: 'DELETE' });
                if (r.ok && window._calendar) window._calendar.refetchEvents();
            },
        },
    ] : [
        {
            label: 'Usuń lekcję', danger: true,
            action: async () => {
                if (!confirm(`Usuń lekcję "${event.title}"?`)) return;
                const r = await fetch(`/api/events/${event.id}`, { method: 'DELETE' });
                if (r.ok) event.remove();
            },
        },
    ];

    items.forEach(item => {
        if (item.divider) {
            const hr = document.createElement('div');
            hr.className = 'border-t border-gray-800 my-1';
            menu.appendChild(hr);
            return;
        }
        const btn = document.createElement('button');
        btn.className = `w-full text-left px-4 py-2 transition-colors ${
            item.danger ? 'text-red-400 hover:bg-red-500/10' : 'text-gray-200 hover:bg-gray-800'
        }`;
        btn.textContent = item.label;
        btn.onclick = () => { menu.remove(); _activeMenu = null; item.action(); };
        menu.appendChild(btn);
    });

    document.body.appendChild(menu);
    _activeMenu = menu;
    setTimeout(() => document.addEventListener('click', () => {
        if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
    }, { once: true }), 0);
}
```

- [ ] **Step 2: Replace `app/templates/teacher/calendar.html`**

```html
{% extends "base.html" %}

{% block title %}Mój Kalendarz — Ekorepetycje{% endblock %}

{% block extra_head %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.css">
{% endblock %}

{% block content %}
<div class="pt-20 pb-16 px-6 max-w-6xl mx-auto">
    <div class="mb-6 flex items-center justify-between">
        <h1 class="text-2xl font-bold text-white">Mój Kalendarz</h1>
        <div class="flex items-center gap-3">
            <button onclick="document.getElementById('unavail-form').classList.toggle('hidden')"
                    class="text-sm border border-gray-700 text-gray-400 hover:text-white px-4 py-2 rounded-xl transition-colors">
                + Zaznacz niedostępność
            </button>
            <a href="/teacher/" class="text-sm text-gray-400 hover:text-white px-3 py-2">← Dashboard</a>
        </div>
    </div>

    <!-- Unavailability form -->
    <div id="unavail-form" class="hidden mb-6 bg-gray-900/50 border border-gray-800/50 rounded-2xl p-5">
        <h3 class="text-sm font-medium text-white mb-3">Nowy blok niedostępności</h3>
        <form class="flex items-end gap-3 flex-wrap" onsubmit="submitUnavailability(event)">
            <div>
                <label class="block text-xs text-gray-400 mb-1">Od</label>
                <input type="datetime-local" id="unavail-start" required
                       class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Do</label>
                <input type="datetime-local" id="unavail-end" required
                       class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none">
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Notatka (opcjonalnie)</label>
                <input type="text" id="unavail-note" placeholder="Wizyta lekarska..."
                       class="bg-gray-800 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none w-48">
            </div>
            <button type="submit"
                    class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-4 py-2 rounded-lg text-sm transition-colors">
                Zapisz
            </button>
        </form>
    </div>

    <div id="calendar" class="bg-gray-900/50 border border-gray-800/50 rounded-2xl p-4"></div>
</div>

{% set is_admin = false %}
{% include "components/series_panel.html" %}
{% endblock %}

{% block extra_scripts %}
<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js"></script>
<script>window.TEACHER_ID = "{{ user.id }}";</script>
<script src="/static/js/series_panel.js"></script>
<script src="/static/js/teacher_calendar.js"></script>
<script>
async function submitUnavailability(e) {
    e.preventDefault();
    const formData = new FormData();
    formData.append('teacher_id', window.TEACHER_ID);
    formData.append('start_time', document.getElementById('unavail-start').value);
    formData.append('end_time', document.getElementById('unavail-end').value);
    formData.append('note', document.getElementById('unavail-note').value);
    const resp = await fetch('/api/availability', { method: 'POST', body: formData });
    if (resp.ok) {
        document.getElementById('unavail-form').classList.add('hidden');
        if (window._calendar) window._calendar.refetchEvents();
    } else {
        alert('Błąd podczas zapisywania.');
    }
}
</script>
<style>
.fc { color: #f3f4f6; }
.fc-theme-standard .fc-scrollgrid { border-color: #1f2937; }
.fc-theme-standard td, .fc-theme-standard th { border-color: #1f2937; }
.fc .fc-col-header-cell-cushion { color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
.fc .fc-daygrid-day-number { color: #6b7280; font-size: 0.875rem; }
.fc .fc-timegrid-slot-label { color: #4b5563; font-size: 0.75rem; }
.fc .fc-toolbar-title { color: #f9fafb; font-size: 1.125rem; font-weight: 600; }
.fc .fc-button { background-color: #1f2937; border-color: #374151; color: #d1d5db; font-size: 0.875rem; padding: 0.375rem 0.75rem; }
.fc .fc-button:hover { background-color: #374151; }
.fc .fc-button-primary:not(:disabled).fc-button-active { background-color: #22c55e; border-color: #22c55e; color: #030712; }
.fc-button.fc-newSeries-button { background-color: #22c55e !important; border-color: #22c55e !important; color: #030712 !important; font-weight: 600; }
.fc-button.fc-newSeries-button:hover { background-color: #16a34a !important; }
.fc .fc-now-indicator-line { border-color: #22c55e; }
</style>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/teacher_calendar.js app/templates/teacher/calendar.html
git commit -m "feat(ui): teacher calendar series panel and context menu"
```

---

## Task 8: Rebuild Tailwind & Run Full Verification

**Files:** None — verification only.

- [ ] **Step 1: Rebuild Tailwind CSS**

```bash
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css --minify
```

Verify `app/static/css/style.css` is updated (check mtime).

- [ ] **Step 2: Run full test suite**

```bash
docker-compose exec web pytest tests/ -v
```

Expected: All tests PASS with output showing:
- `tests/test_security.py` — 3 PASS
- `tests/test_auth.py` — 5 PASS
- `tests/test_admin_users.py` — 1 PASS
- `tests/test_series_schemas.py` — 5 PASS
- `tests/test_series_generation.py` — 13 PASS
- `tests/test_series_api.py` — 3 PASS

- [ ] **Step 3: Smoke test in browser**

Start containers and navigate to `http://localhost:8000/login`. Log in as:
- `admin@ekorepetycje.pl` / `admin123` → verify "New Series" button on calendar, panel opens, teacher dropdown populated
- `anna@ekorepetycje.pl` / `teacher123` → verify "New Series" button on teacher calendar, teacher dropdown hidden

Create a weekly series (Mon+Thu, 10 sessions) as admin. Verify 10 events appear on calendar. Right-click one event mid-series → verify context menu shows "Delete this and following". Delete and verify subsequent events disappear.

- [ ] **Step 4: Final commit**

```bash
git add app/static/css/style.css
git commit -m "chore: rebuild Tailwind CSS for series panel classes"
```

---

## Task 9: Push and Tag

- [ ] **Step 1: Push to origin**

```bash
git push origin main
```

- [ ] **Step 2: Verify on GitHub**

Check that all commits are visible at `https://github.com/maciekgangus/Ekorepetycje`.
