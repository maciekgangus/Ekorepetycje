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
