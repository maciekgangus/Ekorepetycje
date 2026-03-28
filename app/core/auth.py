"""Session cookie signing and FastAPI auth dependencies."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.api.dependencies import get_db
from app.models.users import User, UserRole

_signer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session")
SESSION_COOKIE = "session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


def sign_session(payload: dict[str, Any]) -> str:
    """Serialize and sign a session payload into a cookie-safe string."""
    return _signer.dumps(payload)


def read_session(token: str | None) -> dict[str, Any] | None:
    """Verify and deserialize a signed session token. Returns None on any failure."""
    if not token:
        return None
    try:
        return _signer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Read session cookie and return the corresponding User, or None."""
    token = request.cookies.get(SESSION_COOKIE)
    payload = read_session(token)
    if not payload:
        return None
    try:
        user_id = uuid.UUID(payload["user_id"])
    except (ValueError, KeyError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


class _LoginRedirect(Exception):
    """Raised by auth dependencies to trigger a redirect to /login."""
    pass


def require_auth(user: User | None = Depends(get_current_user)) -> User:
    """Dependency: require any authenticated user. Raises _LoginRedirect if not."""
    if user is None:
        raise _LoginRedirect()
    return user


_ROLE_HOME = {
    UserRole.ADMIN: "/admin/",
    UserRole.TEACHER: "/teacher/",
    UserRole.STUDENT: "/student/",
}


class _WrongRole(Exception):
    """Raised when a logged-in user lacks the required role."""
    def __init__(self, user: "User") -> None:
        self.user = user
        # Eagerly capture the role value so the exception handler can read
        # it even after the SQLAlchemy session has closed (DetachedInstanceError).
        self.role = user.role


def require_role(*roles: UserRole):
    """Dependency factory: require authenticated user with one of the given roles."""
    def _check(user: User = Depends(require_auth)) -> User:
        if user.role not in roles:
            raise _WrongRole(user)
        return user
    return _check


require_admin = require_role(UserRole.ADMIN)
require_teacher_or_admin = require_role(UserRole.TEACHER, UserRole.ADMIN)
