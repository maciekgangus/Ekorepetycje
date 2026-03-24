"""Admin dashboard HTML routes."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_admin
from app.core.security import hash_password
from app.core.templates import templates
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent
from app.models.users import User, UserRole
from app.models.proposals import RescheduleProposal, ProposalStatus

router = APIRouter(prefix="/admin")


async def _pending_count(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count(RescheduleProposal.id))
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
    )).scalar_one()


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(Offering))
    offerings = result.scalars().all()
    pending = await _pending_count(db)
    return templates.TemplateResponse(
        request, "admin/dashboard.html",
        {"offerings": offerings, "pending_proposals": pending},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def admin_calendar(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> HTMLResponse:
    teachers = (await db.execute(
        select(User).where(User.role == UserRole.TEACHER).order_by(User.full_name)
    )).scalars().all()
    students = (await db.execute(
        select(User).where(User.role == UserRole.STUDENT).order_by(User.full_name)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "admin/calendar.html",
        {"user": current_user, "teachers": teachers, "students": students},
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    pending = await _pending_count(db)
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"users": users, "roles": list(UserRole), "pending_proposals": pending},
    )


@router.post("/users/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        result = await db.execute(select(User).order_by(User.role, User.full_name))
        return templates.TemplateResponse(
            request, "admin/users.html",
            {"users": result.scalars().all(),
             "roles": list(UserRole), "pending_proposals": await _pending_count(db),
             "error": f"Użytkownik z adresem {email} już istnieje."},
        )
    user = User(
        full_name=full_name, email=email,
        role=UserRole(role),
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"users": users, "roles": list(UserRole), "pending_proposals": await _pending_count(db)},
    )


@router.post("/users/{user_id}/role", response_class=HTMLResponse)
async def update_user_role(
    request: Request,
    user_id: UUID,
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.role = UserRole(role)
        await db.flush()
    return templates.TemplateResponse(
        request, "components/inline_success.html",
        {"message": "Rola zaktualizowana."},
    )


@router.post("/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_user_password(
    request: Request,
    user_id: UUID,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.hashed_password = hash_password(password)
        await db.flush()
    return templates.TemplateResponse(
        request, "components/inline_success.html",
        {"message": "Hasło zmienione."},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def admin_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(
        select(RescheduleProposal)
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
        .options(selectinload(RescheduleProposal.event), selectinload(RescheduleProposal.proposer))
        .order_by(RescheduleProposal.created_at)
    )
    proposals = result.scalars().all()
    pending = len(proposals)
    return templates.TemplateResponse(
        request, "admin/proposals.html",
        {"proposals": proposals, "pending_proposals": pending},
    )


@router.post("/proposals/{proposal_id}/approve", response_class=HTMLResponse)
async def approve_proposal(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    # NOTE: send_proposal_outcome_email is defined in Task 12 (email.py stubs).
    from app.services.email import send_proposal_outcome_email
    result = await db.execute(
        select(RescheduleProposal).where(RescheduleProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        event_result = await db.execute(
            select(ScheduleEvent).where(ScheduleEvent.id == proposal.event_id)
        )
        event = event_result.scalar_one_or_none()
        if event:
            event.start_time = proposal.new_start
            event.end_time = proposal.new_end
        proposal.status = ProposalStatus.APPROVED
        await db.flush()
        await send_proposal_outcome_email(proposal, approved=True)
    return templates.TemplateResponse(
        request, "components/inline_success.html",
        {"message": "Zaakceptowano."},
    )


@router.post("/proposals/{proposal_id}/reject", response_class=HTMLResponse)
async def reject_proposal(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    from app.services.email import send_proposal_outcome_email
    result = await db.execute(
        select(RescheduleProposal).where(RescheduleProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        proposal.status = ProposalStatus.REJECTED
        await db.flush()
        await send_proposal_outcome_email(proposal, approved=False)
    return templates.TemplateResponse(
        request, "components/inline_success.html",
        {"message": "Odrzucono."},
    )


@router.post("/offerings/create", response_class=HTMLResponse)
async def create_offering_htmx(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    base_price_per_hour: str = Form(...),
    teacher_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        price = Decimal(base_price_per_hour)
        t_id = UUID(teacher_id)
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            request, "components/error_fragment.html",
            {"error": "Nieprawidłowe dane. Sprawdź UUID nauczyciela i cenę."},
            status_code=422,
        )
    offering = Offering(
        title=title, description=description or None,
        base_price_per_hour=price, teacher_id=t_id,
    )
    db.add(offering)
    await db.flush()
    result = await db.execute(select(Offering))
    return templates.TemplateResponse(
        request, "components/offerings_list.html",
        {"offerings": result.scalars().all()},
    )
