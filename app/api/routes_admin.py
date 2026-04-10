"""Admin dashboard HTML routes."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.dependencies import AdminUser, CSRF, DB
from app.core.security import hash_password
from app.core.templates import templates
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent
from app.models.users import User, UserRole

router = APIRouter(prefix="/admin")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: DB,
    _: AdminUser,
) -> HTMLResponse:
    teachers = (await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .options(selectinload(User.offerings))
        .order_by(User.full_name)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "admin/dashboard.html",
        {"teachers": teachers},
    )


@router.get("/offerings/fragment", response_class=HTMLResponse)
async def offerings_fragment(
    request: Request,
    db: DB,
    _: AdminUser,
    teacher_id: str = Query("all"),
) -> HTMLResponse:
    q = (select(User)
         .where(User.role == UserRole.TEACHER)
         .options(selectinload(User.offerings))
         .order_by(User.full_name))
    if teacher_id != "all":
        try:
            q = q.where(User.id == UUID(teacher_id))
        except ValueError:
            pass
    teachers = (await db.execute(q)).scalars().all()
    return templates.TemplateResponse(
        request, "components/offerings_grouped.html",
        {"teachers": teachers},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def admin_calendar(
    request: Request,
    db: DB,
    current_user: AdminUser,
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
    db: DB,
    _: AdminUser,
) -> HTMLResponse:
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"users": users, "roles": [r for r in UserRole if r != UserRole.ADMIN]},
    )


@router.post("/users/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    db: DB,
    _: AdminUser,
    _csrf: CSRF,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse:
    non_admin_roles = [r for r in UserRole if r != UserRole.ADMIN]
    try:
        parsed_role = UserRole(role)
    except ValueError:
        parsed_role = None
    if parsed_role is None or parsed_role == UserRole.ADMIN:
        result = await db.execute(select(User).order_by(User.role, User.full_name))
        return templates.TemplateResponse(
            request, "admin/users.html",
            {"users": result.scalars().all(),
             "roles": non_admin_roles,
             "error": "Nieprawidłowa rola."},
        )
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        result = await db.execute(select(User).order_by(User.role, User.full_name))
        return templates.TemplateResponse(
            request, "admin/users.html",
            {"users": result.scalars().all(),
             "roles": non_admin_roles,
             "error": f"Użytkownik z adresem {email} już istnieje."},
        )
    user = User(
        full_name=full_name, email=email,
        role=parsed_role,
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"users": users, "roles": non_admin_roles},
    )



@router.post("/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_user_password(
    request: Request,
    user_id: UUID,
    db: DB,
    _: AdminUser,
    _csrf: CSRF,
    password: str = Form(...),
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


@router.post("/offerings/create", response_class=HTMLResponse)
async def create_offering_htmx(
    request: Request,
    db: DB,
    _: AdminUser,
    _csrf: CSRF,
    title: str = Form(...),
    description: str = Form(""),
    base_price_per_hour: str = Form(...),
    teacher_id: str = Form(...),
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
    teachers = (await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .options(selectinload(User.offerings))
        .order_by(User.full_name)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "components/offerings_grouped.html",
        {"teachers": teachers},
    )


@router.delete("/offerings/{offering_id}", response_class=HTMLResponse)
async def delete_offering(
    request: Request,
    offering_id: UUID,
    db: DB,
    _: AdminUser,
    _csrf: CSRF,
) -> HTMLResponse:
    offering = await db.get(Offering, offering_id)
    if not offering:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Offering not found")

    event_count = (await db.execute(
        select(func.count(ScheduleEvent.id))
        .where(ScheduleEvent.offering_id == offering_id)
    )).scalar_one()

    if event_count > 0:
        resp = templates.TemplateResponse(
            request, "components/inline_error.html",
            {"error": f"Nie można usunąć — istnieje {event_count} zajęć powiązanych z tą ofertą."},
        )
        resp.headers["HX-Retarget"] = f"#offering-error-{offering_id}"
        resp.headers["HX-Reswap"] = "innerHTML"
        return resp

    await db.delete(offering)
    await db.flush()

    teachers = (await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .options(selectinload(User.offerings))
        .order_by(User.full_name)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "components/offerings_grouped.html",
        {"teachers": teachers},
    )
