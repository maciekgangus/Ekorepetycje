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
