"""JSON API endpoints for FullCalendar hydration and admin data."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.dependencies import get_db
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.schemas.scheduling import ScheduleEventCreate, ScheduleEventRead
from app.schemas.offerings import OfferingCreate, OfferingRead

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/events", response_model=list[ScheduleEventRead])
async def get_events(db: AsyncSession = Depends(get_db)) -> list[ScheduleEventRead]:
    """Return all schedule events for FullCalendar."""
    result = await db.execute(select(ScheduleEvent))
    events = result.scalars().all()
    return [ScheduleEventRead.model_validate(e) for e in events]


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
    return {
        "total_events": total_events,
        "scheduled": scheduled,
        "completed": completed,
        "cancelled": cancelled,
        "total_offerings": total_offerings,
        "total_teachers": total_teachers,
    }
