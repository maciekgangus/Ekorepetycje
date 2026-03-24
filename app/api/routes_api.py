"""JSON API endpoints for FullCalendar hydration and admin data."""

import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_db
from app.core.auth import get_current_user, require_teacher_or_admin
from app.models.availability import UnavailableBlock
from app.models.proposals import RescheduleProposal, ProposalStatus
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.series import RecurringSeries
from app.models.unavail_series import RecurringUnavailSeries
from app.schemas.scheduling import ScheduleEventCreate, ScheduleEventRead
from app.schemas.offerings import OfferingCreate, OfferingRead
from app.schemas.series import RecurringSeriesCreate, RecurringSeriesRead
from app.schemas.unavailability import RecurringUnavailCreate, RecurringUnavailRead
from app.services.series import generate_events
from app.services.unavailability import generate_unavailable_blocks

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/events", response_model=list[ScheduleEventRead])
async def get_events(
    teacher_id: UUID | None = None,
    student_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleEventRead]:
    """Return schedule events for FullCalendar, optionally filtered by teacher or student."""
    q = select(ScheduleEvent)
    if teacher_id:
        q = q.where(ScheduleEvent.teacher_id == teacher_id)
    if student_id:
        q = q.where(ScheduleEvent.student_id == student_id)
    result = await db.execute(q)
    return [ScheduleEventRead.model_validate(e) for e in result.scalars().all()]


@router.post("/events", response_model=ScheduleEventRead, status_code=201)
async def create_event(
    payload: ScheduleEventCreate,
    db: AsyncSession = Depends(get_db),
) -> ScheduleEventRead:
    """Create a new schedule event."""
    event = ScheduleEvent(**payload.model_dump())
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return ScheduleEventRead.model_validate(event)


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


@router.get("/offerings", response_model=list[OfferingRead])
async def get_offerings(db: AsyncSession = Depends(get_db)) -> list[OfferingRead]:
    """Return all offerings."""
    result = await db.execute(select(Offering))
    return [OfferingRead.model_validate(o) for o in result.scalars().all()]


@router.post("/offerings", response_model=OfferingRead, status_code=201)
async def create_offering(
    payload: OfferingCreate,
    db: AsyncSession = Depends(get_db),
) -> OfferingRead:
    """Create a new offering."""
    offering = Offering(**payload.model_dump())
    db.add(offering)
    await db.flush()
    await db.refresh(offering)
    return OfferingRead.model_validate(offering)


@router.get("/availability/{user_id}", response_model=list[dict])
async def get_availability_blocks(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return unavailable blocks for a user (teacher or student) for FullCalendar background rendering."""
    result = await db.execute(
        select(UnavailableBlock).where(UnavailableBlock.user_id == user_id)
    )
    return [
        {
            "id": str(b.id),
            "title": b.note or "Niedostępny",
            "start": b.start_time.isoformat(),
            "end": b.end_time.isoformat(),
            "color": "#6b7280",
            "display": "background",
        }
        for b in result.scalars().all()
    ]


@router.post("/availability", status_code=201)
async def create_availability_block(
    user_id: UUID = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Create a single unavailability block for the given user."""
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(status_code=403)
    block = UnavailableBlock(
        user_id=user_id,
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time),
        note=note or None,
    )
    db.add(block)
    await db.flush()
    await db.refresh(block)
    return {"id": str(block.id)}


@router.get("/teachers", response_model=list[dict])
async def get_teachers(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Return all teachers for dropdown population."""
    result = await db.execute(select(User).where(User.role == UserRole.TEACHER))
    return [{"id": str(u.id), "full_name": u.full_name} for u in result.scalars().all()]


@router.get("/students", response_model=list[dict])
async def get_students(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_teacher_or_admin),
) -> list[dict]:
    """Return all students for dropdown population."""
    result = await db.execute(select(User).where(User.role == UserRole.STUDENT))
    return [{"id": str(u.id), "full_name": u.full_name} for u in result.scalars().all()]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Return statistics for the admin dashboard including revenue and teacher breakdown."""
    now = datetime.now(timezone.utc)

    # ── Month boundaries ──────────────────────────────────────────────────────
    def month_start(y: int, m: int) -> datetime:
        return datetime(y, m, 1, tzinfo=timezone.utc)

    def next_month(y: int, m: int) -> datetime:
        return datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)

    def prev_month(y: int, m: int) -> tuple[int, int]:
        return (y - 1, 12) if m == 1 else (y, m - 1)

    cur_start  = month_start(now.year, now.month)
    cur_end    = next_month(now.year, now.month)
    py, pm     = prev_month(now.year, now.month)
    prev_start = month_start(py, pm)
    prev_end   = cur_start

    # Week boundaries (Mon–Sun)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end   = week_start + timedelta(days=7)

    # ── Revenue helper (completed events × price/h × duration_h) ─────────────
    def _revenue_q(start: datetime, end: datetime):
        return (
            select(func.coalesce(func.sum(
                func.extract('epoch', ScheduleEvent.end_time - ScheduleEvent.start_time)
                / 3600.0 * Offering.base_price_per_hour
            ), 0))
            .select_from(ScheduleEvent)
            .join(Offering, ScheduleEvent.offering_id == Offering.id)
            .where(
                ScheduleEvent.status == EventStatus.COMPLETED,
                ScheduleEvent.start_time >= start,
                ScheduleEvent.start_time < end,
            )
        )

    # ── Basic counts ──────────────────────────────────────────────────────────
    total_events    = (await db.execute(select(func.count(ScheduleEvent.id)))).scalar_one()
    scheduled       = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.SCHEDULED))).scalar_one()
    completed_total = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.COMPLETED))).scalar_one()
    cancelled       = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.CANCELLED))).scalar_one()
    total_teachers  = (await db.execute(select(func.count(User.id)).where(User.role == UserRole.TEACHER))).scalar_one()
    total_students  = (await db.execute(select(func.count(User.id)).where(User.role == UserRole.STUDENT))).scalar_one()
    total_offerings = (await db.execute(select(func.count(Offering.id)))).scalar_one()
    pending_proposals = (await db.execute(select(func.count(RescheduleProposal.id)).where(RescheduleProposal.status == ProposalStatus.PENDING))).scalar_one()

    # ── Lesson counts ─────────────────────────────────────────────────────────
    lessons_this_week  = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.start_time >= week_start, ScheduleEvent.start_time < week_end, ScheduleEvent.status != EventStatus.CANCELLED))).scalar_one()
    lessons_this_month = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.start_time >= cur_start,  ScheduleEvent.start_time < cur_end,  ScheduleEvent.status != EventStatus.CANCELLED))).scalar_one()
    lessons_last_month = (await db.execute(select(func.count(ScheduleEvent.id)).where(ScheduleEvent.start_time >= prev_start, ScheduleEvent.start_time < prev_end, ScheduleEvent.status != EventStatus.CANCELLED))).scalar_one()

    # ── Revenue ───────────────────────────────────────────────────────────────
    revenue_this_month = float((await db.execute(_revenue_q(cur_start, cur_end))).scalar_one())
    revenue_last_month = float((await db.execute(_revenue_q(prev_start, prev_end))).scalar_one())

    # 6-month trend (current month + 5 previous)
    revenue_by_month = []
    for i in range(5, -1, -1):
        y, m = now.year, now.month
        for _ in range(i):
            y, m = prev_month(y, m)
        ms = month_start(y, m)
        me = next_month(y, m)
        rev = float((await db.execute(_revenue_q(ms, me))).scalar_one())
        cnt = (await db.execute(
            select(func.count(ScheduleEvent.id))
            .where(ScheduleEvent.start_time >= ms, ScheduleEvent.start_time < me,
                   ScheduleEvent.status == EventStatus.COMPLETED)
        )).scalar_one()
        revenue_by_month.append({"month": f"{y:04d}-{m:02d}", "revenue": rev, "count": cnt})

    avg_6mo = sum(x["revenue"] for x in revenue_by_month) / 6

    # ── Teacher breakdown (lessons + revenue this month) ──────────────────────
    teacher_rows = (await db.execute(
        select(
            User.full_name,
            func.count(ScheduleEvent.id).label("lessons"),
            func.coalesce(func.sum(
                func.extract('epoch', ScheduleEvent.end_time - ScheduleEvent.start_time)
                / 3600.0 * Offering.base_price_per_hour
            ), 0).label("revenue"),
        )
        .join(ScheduleEvent, ScheduleEvent.teacher_id == User.id)
        .join(Offering, ScheduleEvent.offering_id == Offering.id)
        .where(
            User.role == UserRole.TEACHER,
            ScheduleEvent.start_time >= cur_start,
            ScheduleEvent.start_time < cur_end,
            ScheduleEvent.status != EventStatus.CANCELLED,
        )
        .group_by(User.id, User.full_name)
        .order_by(func.count(ScheduleEvent.id).desc())
    )).all()

    return {
        # legacy fields kept for backwards compat
        "total_events": total_events,
        "scheduled": scheduled,
        "completed": completed_total,
        "cancelled": cancelled,
        "total_offerings": total_offerings,
        "total_teachers": total_teachers,
        "pending_proposals": pending_proposals,
        # new fields
        "total_students": total_students,
        "lessons_this_week": lessons_this_week,
        "lessons_this_month": lessons_this_month,
        "lessons_last_month": lessons_last_month,
        "revenue_this_month": round(revenue_this_month, 2),
        "revenue_last_month": round(revenue_last_month, 2),
        "revenue_6mo_avg": round(avg_6mo, 2),
        "revenue_by_month": revenue_by_month,
        "teacher_stats": [
            {"name": r.full_name, "lessons": r.lessons, "revenue": round(float(r.revenue), 2)}
            for r in teacher_rows
        ],
    }


# ─── Recurring Series ─────────────────────────────────────────────────────────

@router.post("/series", status_code=201)
async def create_series(
    payload: RecurringSeriesCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Create a recurring series and pre-generate all ScheduleEvent rows."""
    if current_user.role != UserRole.ADMIN and payload.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot create series for another teacher")

    series_id = uuid.uuid4()

    try:
        events = generate_events(payload, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not events:
        raise HTTPException(status_code=422, detail="Series would generate zero events. Check start_date and end_date.")

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

    # ── Conflict detection (non-blocking — warnings only) ────────────────────
    conflicts: list[dict] = []
    if events:
        min_start = min(e.start_time for e in events)
        max_end = max(e.end_time for e in events)

        async def _get_blocks(uid: UUID) -> list:
            r = await db.execute(
                select(UnavailableBlock).where(
                    UnavailableBlock.user_id == uid,
                    UnavailableBlock.end_time > min_start,
                    UnavailableBlock.start_time < max_end,
                )
            )
            return r.scalars().all()

        teacher_blocks = await _get_blocks(payload.teacher_id)
        student_blocks = await _get_blocks(payload.student_id) if payload.student_id else []

        for event in events:
            for block in teacher_blocks:
                if block.start_time < event.end_time and block.end_time > event.start_time:
                    conflicts.append({
                        "event_start": event.start_time.isoformat(),
                        "person": "teacher",
                        "note": block.note or "Niedostępność",
                    })
                    break
            for block in student_blocks:
                if block.start_time < event.end_time and block.end_time > event.start_time:
                    conflicts.append({
                        "event_start": event.start_time.isoformat(),
                        "person": "student",
                        "note": block.note or "Niedostępność",
                    })
                    break

    return {"series_id": str(series_id), "events_created": len(events), "conflicts": conflicts}


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

    pivot_result = await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == event_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot:
        raise HTTPException(status_code=404, detail="Event not found")
    if pivot.series_id != series_id:
        raise HTTPException(status_code=404, detail="Event not found in series")

    future_result = await db.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.series_id == series_id,
            ScheduleEvent.start_time >= pivot.start_time,
        )
    )
    for event in future_result.scalars().all():
        await db.delete(event)
    await db.flush()  # flush event deletions before counting remaining

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
    if current_user.role != UserRole.ADMIN and payload.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot reassign series to another teacher")

    pivot_result = await db.execute(
        select(ScheduleEvent).where(ScheduleEvent.id == event_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot:
        raise HTTPException(status_code=404, detail="Event not found")
    if pivot.series_id != series_id:
        raise HTTPException(status_code=404, detail="Event not found in series")

    # Compute ISO-week anchor: Monday of pivot's week
    pivot_date = pivot.start_time.date()
    week_monday = pivot_date - timedelta(days=pivot_date.weekday())

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
    series.teacher_id = payload.teacher_id
    series.student_id = payload.student_id
    series.offering_id = payload.offering_id
    series.title = payload.title
    series.start_date = week_monday
    series.interval_weeks = payload.interval_weeks
    series.day_slots = [s.model_dump() for s in payload.day_slots]
    series.end_date = payload.end_date
    series.end_count = payload.end_count

    db.add_all(new_events)
    await db.flush()

    return {"series_id": str(series_id), "events_updated": len(new_events)}


# ─── Recurring Unavailability Series ──────────────────────────────────────────

@router.post("/unavailability-series", status_code=201)
async def create_unavail_series(
    payload: RecurringUnavailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Create a recurring unavailability series and pre-generate all UnavailableBlock rows."""
    if current_user.role != UserRole.ADMIN and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot create unavailability for another user")

    series_id = uuid.uuid4()

    try:
        blocks = generate_unavailable_blocks(payload, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not blocks:
        raise HTTPException(status_code=422, detail="Series would generate zero blocks.")

    series = RecurringUnavailSeries(
        id=series_id,
        user_id=payload.user_id,
        note=payload.note,
        start_date=payload.start_date,
        interval_weeks=payload.interval_weeks,
        day_slots=[s.model_dump() for s in payload.day_slots],
        end_date=payload.end_date,
        end_count=payload.end_count,
    )
    db.add(series)
    db.add_all(blocks)
    await db.flush()

    return {"series_id": str(series_id), "blocks_created": len(blocks)}


@router.get("/unavailability-series/{series_id}", response_model=RecurringUnavailRead)
async def get_unavail_series(
    series_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> RecurringUnavailRead:
    """Return unavailability series rule for pre-filling the edit panel."""
    result = await db.execute(
        select(RecurringUnavailSeries).where(RecurringUnavailSeries.id == series_id)
    )
    series = result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")
    return RecurringUnavailRead.model_validate(series)


@router.delete("/unavailability-series/{series_id}/from/{block_id}", status_code=204)
async def delete_unavail_series_from(
    series_id: UUID,
    block_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> None:
    """Delete a block and all following blocks in the unavailability series."""
    series_result = await db.execute(
        select(RecurringUnavailSeries).where(RecurringUnavailSeries.id == series_id)
    )
    series = series_result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")

    pivot_result = await db.execute(
        select(UnavailableBlock).where(UnavailableBlock.id == block_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot or pivot.series_id != series_id:
        raise HTTPException(status_code=404, detail="Block not found in series")

    future_result = await db.execute(
        select(UnavailableBlock).where(
            UnavailableBlock.series_id == series_id,
            UnavailableBlock.start_time >= pivot.start_time,
        )
    )
    for block in future_result.scalars().all():
        await db.delete(block)
    await db.flush()

    remaining = (await db.execute(
        select(func.count(UnavailableBlock.id)).where(UnavailableBlock.series_id == series_id)
    )).scalar_one()
    if remaining == 0:
        await db.delete(series)
        await db.flush()


@router.patch("/unavailability-series/{series_id}/from/{block_id}", status_code=200)
async def update_unavail_series_from(
    series_id: UUID,
    block_id: UUID,
    payload: RecurringUnavailCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    """Delete block and all following, re-generate from updated rule starting that ISO week."""
    series_result = await db.execute(
        select(RecurringUnavailSeries).where(RecurringUnavailSeries.id == series_id)
    )
    series = series_result.scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    if current_user.role != UserRole.ADMIN and series.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your series")
    if current_user.role != UserRole.ADMIN and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot reassign series to another user")

    pivot_result = await db.execute(
        select(UnavailableBlock).where(UnavailableBlock.id == block_id)
    )
    pivot = pivot_result.scalar_one_or_none()
    if not pivot or pivot.series_id != series_id:
        raise HTTPException(status_code=404, detail="Block not found in series")

    pivot_date = pivot.start_time.date()
    week_monday = pivot_date - timedelta(days=pivot_date.weekday())

    future_result = await db.execute(
        select(UnavailableBlock).where(
            UnavailableBlock.series_id == series_id,
            UnavailableBlock.start_time >= pivot.start_time,
        )
    )
    for block in future_result.scalars().all():
        await db.delete(block)
    await db.flush()

    regenerate_payload = payload.model_copy(update={"start_date": week_monday})
    try:
        new_blocks = generate_unavailable_blocks(regenerate_payload, series_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    series.user_id = payload.user_id
    series.note = payload.note
    series.start_date = week_monday
    series.interval_weeks = payload.interval_weeks
    series.day_slots = [s.model_dump() for s in payload.day_slots]
    series.end_date = payload.end_date
    series.end_count = payload.end_count

    db.add_all(new_blocks)
    await db.flush()

    return {"series_id": str(series_id), "blocks_updated": len(new_blocks)}


# ─── Teacher profile: photo upload ────────────────────────────────────────────

_PHOTO_DIR = Path(__file__).parent.parent / "static" / "img" / "teachers"
_MAX_PHOTO_BYTES = 2_000_000


@router.post("/teachers/me/photo", response_class=HTMLResponse)
async def upload_own_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Teacher uploads their own profile photo. Returns an HTML <img> fragment."""
    return await _save_teacher_photo(file, current_user, db)


@router.post("/admin/teachers/{teacher_id}/photo", response_class=HTMLResponse)
async def admin_upload_teacher_photo(
    teacher_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Admin uploads a photo for any teacher."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return await _save_teacher_photo(file, teacher, db)


async def _save_teacher_photo(
    file: UploadFile,
    teacher: User,
    db: AsyncSession,
) -> HTMLResponse:
    """Shared logic: validate, convert, save, update DB, return HTML fragment.

    The content_type check is a user-experience hint only — it is client-supplied
    and therefore not a security gate. Pillow's UnidentifiedImageError is the real
    guard against non-image payloads.

    Both bio+specialties are always replaced on PATCH (PUT semantics). The HTMX
    forms in the dashboard submit both fields together, so partial updates do not
    occur in normal usage.
    """
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=422, detail="Only JPEG or PNG images are accepted")
    data = await file.read()
    if len(data) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=422, detail="Image must be under 2 MB")
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(status_code=422, detail="Invalid image file")
    _PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    dest = _PHOTO_DIR / f"{teacher.id}.jpg"
    img.save(dest, format="JPEG", quality=85)
    photo_url = f"/static/img/teachers/{teacher.id}.jpg"
    teacher.photo_url = photo_url
    await db.flush()
    # Use uuid4() as cache-buster so every re-upload produces a fresh URL.
    cache_key = uuid.uuid4()
    return HTMLResponse(
        f'<img id="teacher-photo" src="{photo_url}?v={cache_key}" '
        f'alt="{teacher.full_name}" class="w-20 h-20 object-cover">'
    )


# ─── Teacher profile: bio + specialties ───────────────────────────────────────

@router.patch("/teachers/me/profile")
async def update_own_profile(
    bio: str = Form(default=""),
    specialties: str = Form(default=""),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Teacher updates their own bio and specialties."""
    current_user.bio = bio.strip() or None
    current_user.specialties = specialties.strip() or None
    await db.flush()
    return {"ok": True}


@router.patch("/admin/teachers/{teacher_id}/profile")
async def admin_update_teacher_profile(
    teacher_id: UUID,
    bio: str = Form(default=""),
    specialties: str = Form(default=""),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin updates bio and specialties for any teacher."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    teacher.bio = bio.strip() or None
    teacher.specialties = specialties.strip() or None
    await db.flush()
    return {"ok": True}
