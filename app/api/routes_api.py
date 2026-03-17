"""JSON API endpoints for FullCalendar hydration and admin data."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_db
from app.core.auth import require_teacher_or_admin
from app.models.availability import UnavailableBlock
from app.models.proposals import RescheduleProposal, ProposalStatus
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.schemas.scheduling import ScheduleEventCreate, ScheduleEventRead
from app.schemas.offerings import OfferingCreate, OfferingRead

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
) -> ScheduleEventRead:
    """Update a schedule event (e.g., drag-and-drop reschedule)."""
    result = await db.execute(select(ScheduleEvent).where(ScheduleEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.flush()
    await db.refresh(event)
    return ScheduleEventRead.model_validate(event)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a schedule event."""
    result = await db.execute(select(ScheduleEvent).where(ScheduleEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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


@router.get("/availability/{teacher_id}", response_model=list[dict])
async def get_availability_blocks(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return unavailable blocks for a teacher (for FullCalendar background rendering)."""
    result = await db.execute(
        select(UnavailableBlock).where(UnavailableBlock.teacher_id == teacher_id)
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
    teacher_id: UUID = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    # Ownership check: teachers can only mark unavailability for themselves.
    if current_user.role != UserRole.ADMIN and current_user.id != teacher_id:
        raise HTTPException(status_code=403)
    block = UnavailableBlock(
        teacher_id=teacher_id,
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
    result = await db.execute(
        select(User).where(User.role == UserRole.TEACHER)
    )
    return [{"id": str(u.id), "full_name": u.full_name} for u in result.scalars().all()]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Return basic statistics for the admin dashboard."""
    total_events = (await db.execute(select(func.count(ScheduleEvent.id)))).scalar_one()
    scheduled = (await db.execute(
        select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.SCHEDULED)
    )).scalar_one()
    completed = (await db.execute(
        select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.COMPLETED)
    )).scalar_one()
    cancelled = (await db.execute(
        select(func.count(ScheduleEvent.id)).where(ScheduleEvent.status == EventStatus.CANCELLED)
    )).scalar_one()
    total_offerings = (await db.execute(select(func.count(Offering.id)))).scalar_one()
    total_teachers = (await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.TEACHER)
    )).scalar_one()
    pending_proposals = (await db.execute(
        select(func.count(RescheduleProposal.id))
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
    )).scalar_one()
    return {
        "total_events": total_events,
        "scheduled": scheduled,
        "completed": completed,
        "cancelled": cancelled,
        "total_offerings": total_offerings,
        "total_teachers": total_teachers,
        "pending_proposals": pending_proposals,
    }
