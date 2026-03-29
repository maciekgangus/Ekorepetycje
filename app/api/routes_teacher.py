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
