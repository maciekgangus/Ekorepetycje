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
async def landing_page(request: Request) -> HTMLResponse:
    """Render the main landing page."""
    return templates.TemplateResponse("landing/index.html", {"request": request})


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request) -> HTMLResponse:
    """Render the contact page."""
    return templates.TemplateResponse("landing/contact.html", {"request": request})


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
            "components/contact_error.html",
            {"request": request, "error": "Nieprawidłowy adres e-mail. Sprawdź wpisany adres."},
            status_code=422,
        )
    await send_contact_email(form)
    return templates.TemplateResponse(
        "components/contact_success.html", {"request": request}
    )


# Values are used as ILIKE patterns (%keyword%). Do NOT include SQL LIKE
# metacharacters (%, _) in these strings or filtering will break silently.
_SUBJECT_KEYWORDS: dict[str, str] = {
    "matematyka": "Matematyka",
    "informatyka": "Informatyka",
    "jezyki-obce": "Języki",
}


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
        "landing/subject_detail.html",
        {"request": request, "subject": slug, "keyword": keyword, "teachers": teachers},
    )
