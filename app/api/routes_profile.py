"""User profile routes — change own password."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.auth import require_auth
from app.core.csrf import require_csrf
from app.core.security import hash_password, verify_password
from app.core.templates import templates
from app.models.users import User

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_auth),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "profile.html",
        {"user": current_user},
    )


@router.post("/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
    _csrf: None = Depends(require_csrf),
) -> HTMLResponse:
    if not verify_password(old_password, current_user.hashed_password):
        return templates.TemplateResponse(
            request, "profile.html",
            {"user": current_user, "error": "Nieprawidłowe obecne hasło."},
        )
    current_user.hashed_password = hash_password(new_password)
    await db.flush()
    return templates.TemplateResponse(
        request, "profile.html",
        {"user": current_user, "success": "Hasło zmienione pomyślnie."},
    )
