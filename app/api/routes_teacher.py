"""Teacher-facing HTML routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_teacher_or_admin
from app.core.templates import templates
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.proposals import RescheduleProposal, ProposalStatus
from app.models.users import User
from app.services.email import send_proposal_email

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
        "teacher/dashboard.html",
        {"request": request, "user": current_user, "upcoming": upcoming},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def teacher_calendar(
    request: Request,
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "teacher/calendar.html",
        {"request": request, "user": current_user},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def teacher_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    result = await db.execute(
        select(RescheduleProposal)
        .where(RescheduleProposal.proposed_by == current_user.id)
        .options(selectinload(RescheduleProposal.event))
        .order_by(RescheduleProposal.created_at.desc())
    )
    proposals = result.scalars().all()
    return templates.TemplateResponse(
        "teacher/proposals.html",
        {"request": request, "user": current_user, "proposals": proposals},
    )


@router.post("/proposals/create", response_class=HTMLResponse)
async def create_proposal(
    request: Request,
    event_id: UUID = Form(...),
    new_start: str = Form(...),
    new_end: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    # Ownership check: teacher can only propose reschedule for their own events.
    event_result = await db.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.teacher_id == current_user.id,
        )
    )
    if not event_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    proposal = RescheduleProposal(
        event_id=event_id,
        proposed_by=current_user.id,
        new_start=datetime.fromisoformat(new_start),
        new_end=datetime.fromisoformat(new_end),
        status=ProposalStatus.PENDING,
    )
    db.add(proposal)
    await db.flush()
    await send_proposal_email(current_user, proposal)
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Propozycja przesłana do akceptacji."},
    )
