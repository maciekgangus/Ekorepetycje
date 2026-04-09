"""User profile routes — change own password."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.api.dependencies import CSRF, CurrentUser, DB
from app.core.security import hash_password, verify_password
from app.core.templates import templates

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: CurrentUser,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "profile.html",
        {"user": current_user},
    )


@router.post("/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    db: DB,
    current_user: CurrentUser,
    _csrf: CSRF,
    old_password: str = Form(...),
    new_password: str = Form(...),
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
