"""HTML routes for the public-facing landing pages (Jinja2 + HTMX)."""

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.templates import templates
from app.models.users import User, UserRole
from app.schemas.contact import ContactForm
from app.services.email import send_contact_email

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the main landing page with featured teachers."""
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .where(User.photo_url.isnot(None))
        .where(User.bio.isnot(None))
        .order_by(User.created_at.asc())
        .limit(3)
    )
    featured_teachers = result.scalars().all()
    return templates.TemplateResponse(
        request, "landing/index.html",
        {"featured_teachers": featured_teachers},
    )


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request) -> HTMLResponse:
    """Render the contact page."""
    return templates.TemplateResponse(request, "landing/contact.html")


@router.post("/contact/submit", response_class=HTMLResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
) -> HTMLResponse:
    """Handle contact form submissions and return an HTMX success fragment."""
    try:
        form = ContactForm(name=name, email=email, message=message)
    except ValidationError:
        return templates.TemplateResponse(
            request, "components/contact_error.html",
            {"error": "Nieprawidłowy adres e-mail. Sprawdź wpisany adres."},
            status_code=422,
        )
    await send_contact_email(form)
    return templates.TemplateResponse(request, "components/contact_success.html")


# Values are used as ILIKE patterns (%keyword%). Do NOT include SQL LIKE
# metacharacters (%, _) in these strings or filtering will break silently.
_SUBJECT_KEYWORDS: dict[str, str] = {
    "matematyka": "Matematyka",
    "informatyka": "Informatyka",
    "jezyki-obce": "Języki",
}


@router.get("/nauczyciele", response_class=HTMLResponse)
async def teachers_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the full teachers list page."""
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .order_by(User.created_at.asc())
    )
    teachers = result.scalars().all()
    return templates.TemplateResponse(
        request, "landing/teachers.html",
        {"teachers": teachers},
    )


@router.get("/nauczyciele/{teacher_id}", response_class=HTMLResponse)
async def teacher_profile_page(
    teacher_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render an individual teacher profile page."""
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return templates.TemplateResponse(
        request, "landing/teacher_profile.html",
        {"teacher": teacher},
    )


@router.get("/przedmioty/{slug}", response_class=HTMLResponse)
async def subject_detail(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render a subject detail page with static description and live teacher list."""
    if slug not in _SUBJECT_KEYWORDS:
        raise HTTPException(status_code=404, detail="Subject not found")
    keyword = _SUBJECT_KEYWORDS[slug]
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .where(User.specialties.ilike(f"%{keyword}%"))
        .order_by(User.created_at.asc())
    )
    teachers = result.scalars().all()
    return templates.TemplateResponse(
        request, "landing/subject_detail.html",
        {"subject": slug, "keyword": keyword, "teachers": teachers},
    )
