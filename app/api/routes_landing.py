"""HTML routes for the public-facing landing pages (Jinja2 + HTMX)."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates
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


@router.post("/api/contact", response_class=HTMLResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
) -> HTMLResponse:
    """Handle contact form submissions and return an HTMX success fragment."""
    form = ContactForm(name=name, email=email, message=message)
    await send_contact_email(form)
    return templates.TemplateResponse(
        "components/contact_success.html", {"request": request}
    )
