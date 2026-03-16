"""Admin dashboard HTML routes."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_db
from app.core.templates import templates
from app.models.offerings import Offering

router = APIRouter(prefix="/admin")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request) -> HTMLResponse:
    """Admin overview dashboard with stats."""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


@router.get("/calendar", response_class=HTMLResponse)
async def admin_calendar(request: Request) -> HTMLResponse:
    """FullCalendar view for managing schedule events."""
    return templates.TemplateResponse("admin/calendar.html", {"request": request})


@router.post("/offerings/create", response_class=HTMLResponse)
async def create_offering_htmx(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    base_price_per_hour: str = Form(...),
    teacher_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """HTMX endpoint to create a new offering and return updated list fragment."""
    try:
        price = Decimal(base_price_per_hour)
        t_id = UUID(teacher_id)
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            "components/error_fragment.html",
            {"request": request, "error": "Nieprawidłowe dane. Sprawdź UUID nauczyciela i cenę."},
            status_code=422,
        )

    offering = Offering(
        title=title,
        description=description or None,
        base_price_per_hour=price,
        teacher_id=t_id,
    )
    db.add(offering)
    await db.flush()

    result = await db.execute(select(Offering))
    offerings = result.scalars().all()
    return templates.TemplateResponse(
        "components/offerings_list.html",
        {"request": request, "offerings": offerings},
    )
