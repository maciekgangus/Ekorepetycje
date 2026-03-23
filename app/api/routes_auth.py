"""Authentication routes: login, logout."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_db
from app.core.auth import SESSION_COOKIE, get_current_user, sign_session
from app.core.security import verify_password
from app.core.templates import templates
from app.models.users import User, UserRole

router = APIRouter(tags=["auth"])

_ROLE_REDIRECT = {
    UserRole.ADMIN: "/admin/",
    UserRole.TEACHER: "/teacher/",
    UserRole.STUDENT: "/student/",
}


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> Response:
    """Show login form. Redirect already-authenticated users to their dashboard."""
    if user:
        return RedirectResponse(_ROLE_REDIRECT.get(user.role, "/"), status_code=303)
    return templates.TemplateResponse(request, "auth/login.html")


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Validate credentials, set session cookie, redirect by role."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request, "auth/login.html",
            {"error": "Nieprawidłowy e-mail lub hasło."},
            status_code=200,
        )

    token = sign_session({"user_id": str(user.id), "role": user.role})
    response = RedirectResponse(_ROLE_REDIRECT.get(user.role, "/"), status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    """Clear session cookie and redirect to login."""
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
