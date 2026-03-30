"""HTML routes for the public-facing landing pages (Jinja2 + HTMX)."""

import uuid

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.templates import templates
from app.models.users import User, UserRole
from app.schemas.contact import ContactForm
from app.services.email import send_contact_email

router = APIRouter()

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def _verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Cloudflare Turnstile token server-side. Returns True on success."""
    if not token:
        return False
    payload: dict = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(_TURNSTILE_VERIFY_URL, data=payload)
        return bool(resp.json().get("success", False))
    except Exception:
        return False


def _captcha_error(request: Request, message: str, status: int) -> HTMLResponse:
    """Return an error fragment that HTMX redirects to #contact-error (not the form)."""
    response = templates.TemplateResponse(
        request, "components/contact_error.html",
        {"error": message},
        status_code=status,
    )
    response.headers["HX-Retarget"] = "#contact-error"
    response.headers["HX-Reswap"] = "outerHTML"
    return response


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
        {
            "featured_teachers": featured_teachers,
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY,
            "chat_available": settings.LLM_PROVIDER.lower() in ("ollama", "bedrock"),
        },
    )


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request) -> HTMLResponse:
    """Render the standalone contact page."""
    return templates.TemplateResponse(
        request, "landing/contact.html",
        {"turnstile_site_key": settings.TURNSTILE_SITE_KEY},
    )


@router.post("/contact/submit", response_class=HTMLResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(""),
    message: str = Form(...),
    cf_turnstile_response: str = Form(""),
) -> HTMLResponse:
    """Handle contact form submission with Turnstile verification."""
    # 1 — Verify CAPTCHA
    client_ip = request.client.host if request.client else None
    if not await _verify_turnstile(cf_turnstile_response, client_ip):
        return _captcha_error(
            request,
            "Weryfikacja CAPTCHA nie powiodła się. Odśwież stronę i spróbuj ponownie.",
            400,
        )

    # 2 — Validate fields
    try:
        form = ContactForm(name=name, email=email, subject=subject, message=message)
    except ValidationError:
        return _captcha_error(
            request,
            "Nieprawidłowy adres e-mail. Sprawdź wpisany adres.",
            422,
        )

    # 3 — Send email (falls back to logging if RESEND_API_KEY is not set)
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
