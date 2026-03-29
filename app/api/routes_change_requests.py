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

    # Invalidate Redis cache (Plan 1 integration).
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
