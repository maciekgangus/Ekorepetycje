"""FastAPI dependency providers and reusable Annotated type aliases."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin, require_auth, require_role, require_teacher_or_admin
from app.models.users import UserRole as _UserRole
from app.core.csrf import require_csrf
from app.db.database import get_db
from app.models.users import User

# Re-export get_db so existing imports like `from app.api.dependencies import get_db` still work.
__all__ = ["get_db", "DB", "CurrentUser", "AdminUser", "TeacherUser", "StudentUser", "CSRF"]

# ── Annotated shortcuts — use these instead of repeating Depends() in every route ──
DB          = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_auth)]
AdminUser   = Annotated[User, Depends(require_admin)]
TeacherUser = Annotated[User, Depends(require_teacher_or_admin)]
StudentUser = Annotated[User, Depends(require_role(_UserRole.STUDENT))]
CSRF        = Annotated[None, Depends(require_csrf)]
