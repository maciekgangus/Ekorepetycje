# Auth & Role-Based Admin Panel — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-based authentication and role-differentiated dashboards (admin / teacher / student) with user management, availability blocks, and reschedule proposals.

**Architecture:** Signed cookie sessions via `itsdangerous` + `passlib[bcrypt]`. FastAPI dependency injection for auth guards. Separate Jinja2 route files and templates per role. New `UnavailableBlock` and `RescheduleProposal` models with Alembic migration.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Jinja2, HTMX, Tailwind CSS, passlib[bcrypt], itsdangerous, pytest, pytest-asyncio, httpx

**Spec:** `docs/specs/2026-03-17-auth-and-admin-design.md`

---

## Branch setup

Before any work:
```bash
git checkout main && git pull
git checkout -b feature/auth-and-admin
```

All builds in Docker:
```bash
docker-compose up -d
docker-compose exec web alembic upgrade head   # migrations
docker run --rm -v "$(pwd):/app:z" -w /app node:20-alpine \
  sh -c "npm install tailwindcss@3.4.0 && ./node_modules/.bin/tailwindcss \
  -i ./app/static/css/input.css -o ./app/static/css/style.css"  # CSS rebuild
```

---

## File Map

### New files
| Path | Responsibility |
|------|---------------|
| `app/core/security.py` | `hash_password`, `verify_password` (passlib) |
| `app/core/auth.py` | `sign_session`, `read_session`, `get_current_user`, `require_role` deps |
| `app/api/routes_auth.py` | `GET/POST /login`, `POST /logout` |
| `app/api/routes_profile.py` | `GET/POST /profile` (change own password) |
| `app/api/routes_teacher.py` | `/teacher/*` — dashboard, calendar, proposals |
| `app/api/routes_student.py` | `/student/` — read-only appointment list |
| `app/models/availability.py` | `UnavailableBlock` ORM model |
| `app/models/proposals.py` | `RescheduleProposal` ORM model |
| `app/schemas/availability.py` | Pydantic schemas for availability blocks |
| `app/schemas/proposals.py` | Pydantic schemas for reschedule proposals |
| `app/templates/auth/login.html` | Login page (navy, editorial) |
| `app/templates/profile.html` | Change own password |
| `app/templates/errors/403.html` | Forbidden page |
| `app/templates/admin/users.html` | User management table |
| `app/templates/admin/proposals.html` | Pending proposals list |
| `app/templates/teacher/dashboard.html` | Teacher upcoming sessions |
| `app/templates/teacher/calendar.html` | Teacher calendar + unavailable blocks |
| `app/templates/teacher/proposals.html` | Teacher's sent proposals + status |
| `app/templates/student/dashboard.html` | Student read-only appointments |
| `app/templates/components/navbar_admin.html` | Dark admin nav with proposals badge |
| `scripts/seed.py` | Demo data: 1 admin, 2 teachers, 2 students, offerings, events |
| `tests/conftest.py` | pytest fixtures: async test client, db session |
| `tests/test_auth.py` | Login / logout / guard tests |
| `tests/test_admin_users.py` | User CRUD tests |
| `tests/test_proposals.py` | Reschedule proposal flow tests |

### Modified files
| Path | Change |
|------|--------|
| `requirements.txt` | Add `passlib[bcrypt]`, `itsdangerous`, `pytest`, `pytest-asyncio` |
| `app/main.py` | Register new routers; session middleware |
| `app/models/__init__.py` | Import new models so Alembic sees them |
| `app/api/routes_admin.py` | Add `/admin/users`, `/admin/proposals`; add auth guards |
| `app/api/routes_api.py` | Add `pending_proposals` to `/api/stats`; availability block endpoints |
| `app/templates/base.html` | Pass `request.state.user` context; admin nav override |
| `app/templates/admin/dashboard.html` | Proposals badge on header |
| `app/static/js/admin_calendar.js` | Read teacher filter param; render unavailable blocks |

---

## Chunk 1: Dependencies, security utils, session auth core

### Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] Add to `requirements.txt`:
```
passlib[bcrypt]
itsdangerous
pytest
pytest-asyncio
anyio[trio]
```

- [ ] Create `pytest.ini` in project root:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] Rebuild container:
```bash
docker-compose up -d --build
```

- [ ] Verify inside container:
```bash
docker-compose exec web python -c "import passlib, itsdangerous; print('ok')"
```
Expected: `ok`

- [ ] Commit:
```bash
git add requirements.txt
git commit -m "chore(deps): add passlib, itsdangerous, pytest"
```

---

### Task 2: Password hashing utility

**Files:**
- Create: `app/core/security.py`
- Create: `tests/conftest.py`
- Create: `tests/test_security.py`

- [ ] Create `tests/conftest.py`:
```python
# pytest-asyncio is configured via pytest.ini (asyncio_mode = auto).
# Add shared fixtures here when needed.
```

- [ ] Create `tests/test_security.py`:
```python
from app.core.security import hash_password, verify_password

def test_hash_is_not_plaintext():
    h = hash_password("secret123")
    assert h != "secret123"

def test_verify_correct_password():
    h = hash_password("secret123")
    assert verify_password("secret123", h) is True

def test_verify_wrong_password():
    h = hash_password("secret123")
    assert verify_password("wrong", h) is False
```

- [ ] Run to confirm failure:
```bash
docker-compose exec web pytest tests/test_security.py -v
```
Expected: `ImportError` (module doesn't exist yet)

- [ ] Create `app/core/security.py`:
```python
"""Password hashing utilities using passlib/bcrypt."""

from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of plain-text password."""
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored bcrypt hash."""
    return _ctx.verify(plain, hashed)
```

- [ ] Run tests:
```bash
docker-compose exec web pytest tests/test_security.py -v
```
Expected: 3 PASSED

- [ ] Commit:
```bash
git add app/core/security.py tests/
git commit -m "feat(auth): add bcrypt password hashing utility"
```

---

### Task 3: Session signing and current-user dependency

**Files:**
- Create: `app/core/auth.py`
- Create: `tests/test_auth.py` (stub)

- [ ] Create `tests/test_auth.py`:
```python
from app.core.auth import sign_session, read_session

def test_sign_and_read_roundtrip():
    payload = {"user_id": "abc-123", "role": "admin"}
    token = sign_session(payload)
    assert isinstance(token, str)
    result = read_session(token)
    assert result == payload

def test_read_tampered_token_returns_none():
    result = read_session("tampered.garbage.token")
    assert result is None

def test_read_empty_token_returns_none():
    assert read_session("") is None
    assert read_session(None) is None
```

- [ ] Run to confirm failure:
```bash
docker-compose exec web pytest tests/test_auth.py -v
```
Expected: `ImportError`

- [ ] Create `app/core/auth.py`:
```python
"""Session cookie signing and FastAPI auth dependencies."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
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


def require_role(*roles: UserRole):
    """Dependency factory: require authenticated user with one of the given roles."""
    def _check(user: User = Depends(require_auth)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return user
    return _check


require_admin = require_role(UserRole.ADMIN)
require_teacher_or_admin = require_role(UserRole.TEACHER, UserRole.ADMIN)
```

- [ ] Run tests:
```bash
docker-compose exec web pytest tests/test_auth.py -v
```
Expected: 3 PASSED

- [ ] Commit:
```bash
git add app/core/auth.py tests/test_auth.py
git commit -m "feat(auth): add session signing and require_role dependencies"
```

---

## Chunk 2: Login / logout routes + login template

### Task 4: Login and logout routes

**Files:**
- Create: `app/api/routes_auth.py`
- Modify: `app/main.py`
- Create: `app/templates/auth/login.html`

- [ ] Add to `tests/test_auth.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_get_login_page_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/login")
    assert r.status_code == 200
    assert "Zaloguj" in r.text

async def test_login_wrong_credentials_returns_form_with_error():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/login", data={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 200
    assert "Nieprawidłowy" in r.text
```
Note: `asyncio_mode = auto` in `pytest.ini` means async test functions are detected automatically — no `@pytest.mark.asyncio` decorator needed.

- [ ] Create `app/api/routes_auth.py`:
```python
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
) -> Response:  # Response (not HTMLResponse) because it may return a RedirectResponse
    """Show login form. Redirect already-authenticated users to their dashboard."""
    if user:
        return RedirectResponse(_ROLE_REDIRECT.get(user.role, "/"), status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request})


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
            "auth/login.html",
            {"request": request, "error": "Nieprawidłowy e-mail lub hasło."},
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
```

- [ ] Register in `app/main.py` — also add the `_LoginRedirect` exception handler:
```python
from fastapi.responses import RedirectResponse
from app.api import routes_auth, routes_profile, routes_teacher, routes_student
from app.core.auth import _LoginRedirect

app.include_router(routes_auth.router)
app.include_router(routes_profile.router)
app.include_router(routes_teacher.router)
app.include_router(routes_student.router)

@app.exception_handler(_LoginRedirect)
async def login_redirect_handler(request, exc):
    return RedirectResponse("/login", status_code=303)
```
(routes_profile, routes_teacher, routes_student will be stubs at first — create them with just a router object)

- [ ] Create stub routers (so import doesn't fail):
```python
# app/api/routes_profile.py
from fastapi import APIRouter
router = APIRouter()

# app/api/routes_teacher.py
from fastapi import APIRouter
router = APIRouter(prefix="/teacher")

# app/api/routes_student.py
from fastapi import APIRouter
router = APIRouter(prefix="/student")
```

- [ ] Create `app/templates/auth/login.html`:
```html
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Logowanie — Ekorepetycje</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body class="bg-navy min-h-screen flex items-center justify-center font-sans">
    <div class="w-full max-w-sm px-6 py-12">
        <div class="mb-10 text-center">
            <a href="/" class="font-serif text-2xl font-semibold text-cream">Ekorepetycje</a>
            <p class="text-cream/40 text-sm mt-2 tracking-wide">Panel administracyjny</p>
        </div>

        {% if error %}
        <div class="mb-6 text-sm text-red-400 border border-red-400/20 bg-red-400/10 px-4 py-3">
            {{ error }}
        </div>
        {% endif %}

        <form method="post" action="/login" class="space-y-5">
            <div>
                <label class="block text-xs font-medium text-cream/50 tracking-widest uppercase mb-2">E-mail</label>
                <input type="email" name="email" required autofocus
                       class="w-full bg-cream/5 border border-cream/15 px-4 py-3 text-cream placeholder-cream/25 focus:outline-none focus:border-cream/40 text-sm"
                       placeholder="jan@example.com">
            </div>
            <div>
                <label class="block text-xs font-medium text-cream/50 tracking-widest uppercase mb-2">Hasło</label>
                <input type="password" name="password" required
                       class="w-full bg-cream/5 border border-cream/15 px-4 py-3 text-cream placeholder-cream/25 focus:outline-none focus:border-cream/40 text-sm">
            </div>
            <button type="submit"
                    class="w-full bg-cream hover:bg-cream/90 text-navy font-medium py-3 text-sm tracking-wide transition-colors mt-2">
                Zaloguj się
            </button>
        </form>
    </div>
</body>
</html>
```

- [ ] Restart container and test manually:
```bash
docker-compose restart web
# visit http://localhost:8000/login
```
Expected: navy login page with Playfair logo

- [ ] Run tests:
```bash
docker-compose exec web pytest tests/test_auth.py -v
```
Expected: all PASSED

- [ ] Commit:
```bash
git add app/api/routes_auth.py app/api/routes_profile.py \
        app/api/routes_teacher.py app/api/routes_student.py \
        app/main.py app/templates/auth/ tests/test_auth.py
git commit -m "feat(auth): login/logout routes and login template"
```

---

## Chunk 3: New models + Alembic migration

### Task 5: UnavailableBlock model

**Files:**
- Create: `app/models/availability.py`
- Modify: `app/models/__init__.py`

- [ ] Create `app/models/availability.py`:
```python
"""UnavailableBlock ORM model — marks a teacher as unavailable for a time period."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User


class UnavailableBlock(Base):
    """A period during which a teacher is unavailable for sessions."""

    __tablename__ = "unavailable_blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    teacher: Mapped["User"] = relationship("User", foreign_keys=[teacher_id])
```

---

### Task 6: RescheduleProposal model

**Files:**
- Create: `app/models/proposals.py`

- [ ] Create `app/models/proposals.py`:
```python
"""RescheduleProposal ORM model."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Enum as SAEnum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.users import User
    from app.models.scheduling import ScheduleEvent


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RescheduleProposal(Base):
    """A teacher's request to move an existing session to a new time slot."""

    __tablename__ = "reschedule_proposals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedule_events.id"), nullable=False)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    new_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    new_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus), nullable=False,
        default=ProposalStatus.PENDING,
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )

    event: Mapped["ScheduleEvent"] = relationship("ScheduleEvent", foreign_keys=[event_id])
    proposer: Mapped["User"] = relationship("User", foreign_keys=[proposed_by])
```

- [ ] Update `app/models/__init__.py` to import new models (so Alembic autogenerates them):
```python
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.availability import UnavailableBlock
from app.models.proposals import RescheduleProposal, ProposalStatus

__all__ = [
    "User", "UserRole",
    "Offering",
    "ScheduleEvent", "EventStatus",
    "UnavailableBlock",
    "RescheduleProposal", "ProposalStatus",
]
```

- [ ] Generate migration:
```bash
docker-compose exec web alembic revision --autogenerate -m "add unavailable blocks and reschedule proposals"
```
Expected: new file in `alembic/versions/`

- [ ] Inspect the generated migration — verify it creates both tables with correct columns and FK constraints.

- [ ] Apply migration:
```bash
docker-compose exec web alembic upgrade head
```
Expected: no errors

- [ ] Verify tables exist:
```bash
docker-compose exec db psql -U postgres -d ekorepetycje -c "\dt"
```
Expected: `unavailable_blocks` and `reschedule_proposals` in list

- [ ] Commit:
```bash
git add app/models/ alembic/versions/
git commit -m "feat(models): add UnavailableBlock and RescheduleProposal with migration"
```

---

## Chunk 4: Seed data script

### Task 7: Seed script

**Files:**
- Create: `scripts/seed.py`

- [ ] Create `scripts/seed.py`:
```python
"""Seed the database with demo data for development and testing."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.availability import UnavailableBlock

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

NOW = datetime.now(timezone.utc)


async def seed():
    async with AsyncSessionLocal() as db:
        # --- Users ---
        admin = User(
            id=uuid.uuid4(), role=UserRole.ADMIN,
            email="admin@ekorepetycje.pl", full_name="Admin Główny",
            hashed_password=hash_password("admin123"),
        )
        teacher1 = User(
            id=uuid.uuid4(), role=UserRole.TEACHER,
            email="anna@ekorepetycje.pl", full_name="Anna Kowalska",
            hashed_password=hash_password("teacher123"),
        )
        teacher2 = User(
            id=uuid.uuid4(), role=UserRole.TEACHER,
            email="marek@ekorepetycje.pl", full_name="Marek Nowak",
            hashed_password=hash_password("teacher123"),
        )
        student1 = User(
            id=uuid.uuid4(), role=UserRole.STUDENT,
            email="student1@example.com", full_name="Piotr Wiśniewski",
            hashed_password=hash_password("student123"),
        )
        student2 = User(
            id=uuid.uuid4(), role=UserRole.STUDENT,
            email="student2@example.com", full_name="Karolina Dąbrowska",
            hashed_password=hash_password("student123"),
        )
        db.add_all([admin, teacher1, teacher2, student1, student2])
        await db.flush()

        # --- Offerings ---
        off1 = Offering(
            id=uuid.uuid4(), title="Matematyka — Matura Rozszerzona",
            description="Intensywne przygotowanie do matury rozszerzonej.",
            base_price_per_hour=80, teacher_id=teacher1.id,
        )
        off2 = Offering(
            id=uuid.uuid4(), title="Angielski B2–C1",
            description="Konwersacje i przygotowanie do Cambridge FCE/CAE.",
            base_price_per_hour=70, teacher_id=teacher2.id,
        )
        db.add_all([off1, off2])
        await db.flush()

        # --- Schedule Events ---
        events = [
            ScheduleEvent(
                id=uuid.uuid4(), title="Matematyka — Piotr W.",
                start_time=NOW + timedelta(days=1, hours=10),
                end_time=NOW + timedelta(days=1, hours=11),
                offering_id=off1.id, teacher_id=teacher1.id, student_id=student1.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Matematyka — Karolina D.",
                start_time=NOW + timedelta(days=2, hours=14),
                end_time=NOW + timedelta(days=2, hours=15),
                offering_id=off1.id, teacher_id=teacher1.id, student_id=student2.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Angielski — Piotr W.",
                start_time=NOW + timedelta(days=3, hours=9),
                end_time=NOW + timedelta(days=3, hours=10),
                offering_id=off2.id, teacher_id=teacher2.id, student_id=student1.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Angielski — Karolina D.",
                start_time=NOW - timedelta(days=5, hours=10),
                end_time=NOW - timedelta(days=5, hours=11),
                offering_id=off2.id, teacher_id=teacher2.id, student_id=student2.id,
                status=EventStatus.COMPLETED,
            ),
        ]
        db.add_all(events)
        await db.flush()

        # --- Unavailable blocks ---
        db.add(UnavailableBlock(
            id=uuid.uuid4(), teacher_id=teacher1.id,
            start_time=NOW + timedelta(days=4, hours=8),
            end_time=NOW + timedelta(days=4, hours=12),
            note="Wizyta lekarska",
        ))
        await db.commit()
        print("Seed complete.")
        print(f"  admin:   admin@ekorepetycje.pl / admin123")
        print(f"  teacher: anna@ekorepetycje.pl / teacher123")
        print(f"  teacher: marek@ekorepetycje.pl / teacher123")
        print(f"  student: student1@example.com / student123")
        print(f"  student: student2@example.com / student123")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] Run seed:
```bash
docker-compose exec web python scripts/seed.py
```
Expected: prints credential summary with no errors

- [ ] Verify data in DB:
```bash
docker-compose exec db psql -U postgres -d ekorepetycje -c "SELECT email, role FROM users;"
```
Expected: 5 rows (1 admin, 2 teachers, 2 students)

- [ ] Test login works with seeded admin:
```
Visit http://localhost:8000/login
Email: admin@ekorepetycje.pl
Password: admin123
```
Expected: redirect to `/admin/` (currently shows existing dashboard)

- [ ] Commit:
```bash
git add scripts/seed.py
git commit -m "feat(seed): add demo data script with users, offerings, events"
```

---

## Chunk 5: Admin — user management & auth guards

### Task 8: Protect existing admin routes + add user management

**Files:**
- Modify: `app/api/routes_admin.py`
- Create: `app/templates/admin/users.html`
- Modify: `app/templates/admin/dashboard.html` (add proposals badge)
- Modify: `app/templates/components/navbar_admin.html` (create)

- [ ] Add test:
```python
# tests/test_admin_users.py
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_admin_users_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/admin/users", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers["location"]
```

- [ ] **Prerequisite:** Add email stubs to `app/services/email.py` now (full implementation in Task 12) so approve/reject imports don't fail:
```python
async def send_proposal_email(teacher, proposal) -> None:
    pass

async def send_proposal_outcome_email(proposal, approved: bool) -> None:
    pass
```

- [ ] Add to `app/api/routes_admin.py` — protect all routes + add user management:
  - Import `require_admin` from `app.core.auth`
  - Add `Depends(require_admin)` to `admin_dashboard`, `admin_calendar`, `create_offering_htmx`
  - Add `GET /admin/users` — fetch all users, render `admin/users.html`
  - Add `POST /admin/users/create` — HTMX: create user, return updated table fragment
  - Add `PATCH /admin/users/{user_id}/role` — HTMX: update role inline
  - Add `POST /admin/users/{user_id}/reset-password` — admin resets password

- [ ] Full updated `app/api/routes_admin.py`:
```python
"""Admin dashboard HTML routes."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_admin
from app.core.security import hash_password
from app.core.templates import templates
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent
from app.models.users import User, UserRole
from app.models.proposals import RescheduleProposal, ProposalStatus

router = APIRouter(prefix="/admin")


async def _pending_count(db: AsyncSession) -> int:
    from sqlalchemy import func
    return (await db.execute(
        select(func.count(RescheduleProposal.id))
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
    )).scalar_one()


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(Offering))
    offerings = result.scalars().all()
    pending = await _pending_count(db)
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "offerings": offerings, "pending_proposals": pending},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def admin_calendar(
    request: Request,
    _: User = Depends(require_admin),
) -> HTMLResponse:
    return templates.TemplateResponse("admin/calendar.html", {"request": request})


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    pending = await _pending_count(db)
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users, "roles": list(UserRole), "pending_proposals": pending},
    )


@router.post("/users/create", response_class=HTMLResponse)
async def create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    # Guard against duplicate emails (unique constraint on users.email)
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        result = await db.execute(select(User).order_by(User.role, User.full_name))
        return templates.TemplateResponse(
            "admin/users.html",
            {"request": request, "users": result.scalars().all(),
             "roles": list(UserRole), "pending_proposals": await _pending_count(db),
             "error": f"Użytkownik z adresem {email} już istnieje."},
        )
    user = User(
        full_name=full_name, email=email,
        role=UserRole(role),
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    result = await db.execute(select(User).order_by(User.role, User.full_name))
    users = result.scalars().all()
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "users": users, "roles": list(UserRole), "pending_proposals": await _pending_count(db)},
    )


@router.post("/users/{user_id}/role", response_class=HTMLResponse)
async def update_user_role(
    request: Request,
    user_id: UUID,
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.role = UserRole(role)
        await db.flush()
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Rola zaktualizowana."},
    )


@router.post("/users/{user_id}/reset-password", response_class=HTMLResponse)
async def reset_user_password(
    request: Request,
    user_id: UUID,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.hashed_password = hash_password(password)
        await db.flush()
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Hasło zmienione."},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def admin_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    result = await db.execute(
        select(RescheduleProposal)
        .where(RescheduleProposal.status == ProposalStatus.PENDING)
        .options(selectinload(RescheduleProposal.event), selectinload(RescheduleProposal.proposer))
        .order_by(RescheduleProposal.created_at)
    )
    proposals = result.scalars().all()
    pending = len(proposals)
    return templates.TemplateResponse(
        "admin/proposals.html",
        {"request": request, "proposals": proposals, "pending_proposals": pending},
    )


@router.post("/proposals/{proposal_id}/approve", response_class=HTMLResponse)
async def approve_proposal(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    # NOTE: send_proposal_outcome_email is defined in Task 12. The email service
    # stubs must exist before testing approve/reject (run Task 12 first, or
    # create an empty stub in app/services/email.py now and fill it in Task 12).
    from app.services.email import send_proposal_outcome_email
    result = await db.execute(
        select(RescheduleProposal).where(RescheduleProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        event_result = await db.execute(
            select(ScheduleEvent).where(ScheduleEvent.id == proposal.event_id)
        )
        event = event_result.scalar_one_or_none()
        if event:
            event.start_time = proposal.new_start
            event.end_time = proposal.new_end
        proposal.status = ProposalStatus.APPROVED
        await db.flush()
        await send_proposal_outcome_email(proposal, approved=True)
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Zaakceptowano."},
    )


@router.post("/proposals/{proposal_id}/reject", response_class=HTMLResponse)
async def reject_proposal(
    request: Request,
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    from app.services.email import send_proposal_outcome_email
    result = await db.execute(
        select(RescheduleProposal).where(RescheduleProposal.id == proposal_id)
    )
    proposal = result.scalar_one_or_none()
    if proposal and proposal.status == ProposalStatus.PENDING:
        proposal.status = ProposalStatus.REJECTED
        await db.flush()
        await send_proposal_outcome_email(proposal, approved=False)
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Odrzucono."},
    )


@router.post("/offerings/create", response_class=HTMLResponse)
async def create_offering_htmx(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    base_price_per_hour: str = Form(...),
    teacher_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> HTMLResponse:
    try:
        price = Decimal(base_price_per_hour)
        t_id = UUID(teacher_id)
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            "components/error_fragment.html",
            {"request": request, "error": "Nieprawidłowe dane."},
            status_code=422,
        )
    offering = Offering(
        title=title, description=description or None,
        base_price_per_hour=price, teacher_id=t_id,
    )
    db.add(offering)
    await db.flush()
    result = await db.execute(select(Offering))
    return templates.TemplateResponse(
        "components/offerings_list.html",
        {"request": request, "offerings": result.scalars().all()},
    )
```

- [ ] Create `app/templates/components/inline_success.html`:
```html
<p class="text-sm text-green-400 py-2">{{ message }}</p>
```

- [ ] Create `app/templates/admin/users.html` — table of all users with create form, role badge, reset password inline. Follow dark admin theme. Key elements:
  - Page heading "Użytkownicy"
  - Table: Full name | Email | Role (badge colored by role) | Actions
  - Actions per row: "Reset hasła" (inline form via HTMX `hx-post`)
  - "Nowy użytkownik" button → toggleable form: name, email, role select, password
  - Use `hx-post="/admin/users/create" hx-target="body" hx-swap="outerHTML"` on create form

- [ ] Create `app/templates/admin/proposals.html` — list of pending proposals. Key elements:
  - Each row: teacher name, original event title + time, proposed new time
  - Approve / Reject buttons via HTMX

- [ ] Create `app/templates/components/navbar_admin.html`:
```html
<nav class="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-gray-950/80 border-b border-gray-800/50">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="/admin/" class="text-xl font-semibold tracking-tight text-white hover:text-green-400 transition-colors">
            Ekorepetycje <span class="text-xs text-gray-500 font-normal ml-1">admin</span>
        </a>
        <div class="flex items-center gap-6">
            <a href="/admin/" class="text-sm text-gray-400 hover:text-white transition-colors">Dashboard</a>
            <a href="/admin/users" class="text-sm text-gray-400 hover:text-white transition-colors">Użytkownicy</a>
            <a href="/admin/calendar" class="text-sm text-gray-400 hover:text-white transition-colors">Kalendarz</a>
            <a href="/admin/proposals" class="relative text-sm text-gray-400 hover:text-white transition-colors">
                Propozycje
                {% if pending_proposals and pending_proposals > 0 %}
                <span class="absolute -top-1 -right-3 w-4 h-4 bg-red-500 text-white text-[10px] flex items-center justify-center rounded-full">
                    {{ pending_proposals }}
                </span>
                {% endif %}
            </a>
            <form method="post" action="/logout" class="inline">
                <button class="text-sm text-gray-500 hover:text-white transition-colors">Wyloguj</button>
            </form>
        </div>
    </div>
</nav>
```

- [ ] Update admin templates to `{% block navbar %}{% include "components/navbar_admin.html" %}{% endblock %}` and pass `pending_proposals` context.

- [ ] Run tests:
```bash
docker-compose exec web pytest tests/test_admin_users.py -v
```
Expected: PASSED

- [ ] Commit:
```bash
git add app/api/routes_admin.py app/templates/admin/ \
        app/templates/components/navbar_admin.html \
        app/templates/components/inline_success.html
git commit -m "feat(admin): user management, proposals, auth guards, admin navbar"
```

---

## Chunk 6: Teacher views + availability + reschedule proposal

### Task 9: Teacher dashboard, calendar, proposals

**Files:**
- Modify: `app/api/routes_teacher.py`
- Modify: `app/api/routes_api.py` (availability endpoints)
- Create: `app/templates/teacher/dashboard.html`
- Create: `app/templates/teacher/calendar.html`
- Create: `app/templates/teacher/proposals.html`

- [ ] Update `app/api/routes_teacher.py`:
```python
"""Teacher-facing HTML routes."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_teacher_or_admin, get_current_user
from app.core.templates import templates
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.proposals import RescheduleProposal, ProposalStatus
from app.models.availability import UnavailableBlock
from app.models.users import User
from app.services.email import send_proposal_email

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/", response_class=HTMLResponse)
async def teacher_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleEvent)
        .where(
            ScheduleEvent.teacher_id == current_user.id,
            ScheduleEvent.start_time >= now,
            ScheduleEvent.status == EventStatus.SCHEDULED,
        )
        .options(selectinload(ScheduleEvent.student), selectinload(ScheduleEvent.offering))
        .order_by(ScheduleEvent.start_time)
        .limit(10)
    )
    upcoming = result.scalars().all()
    return templates.TemplateResponse(
        "teacher/dashboard.html",
        {"request": request, "user": current_user, "upcoming": upcoming},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def teacher_calendar(
    request: Request,
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        "teacher/calendar.html",
        {"request": request, "user": current_user},
    )


@router.get("/proposals", response_class=HTMLResponse)
async def teacher_proposals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    result = await db.execute(
        select(RescheduleProposal)
        .where(RescheduleProposal.proposed_by == current_user.id)
        .options(selectinload(RescheduleProposal.event))
        .order_by(RescheduleProposal.created_at.desc())
    )
    proposals = result.scalars().all()
    return templates.TemplateResponse(
        "teacher/proposals.html",
        {"request": request, "user": current_user, "proposals": proposals},
    )


@router.post("/proposals/create", response_class=HTMLResponse)
async def create_proposal(
    request: Request,
    event_id: UUID = Form(...),
    new_start: str = Form(...),
    new_end: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> HTMLResponse:
    # Ownership check: teacher can only propose reschedule for their own events.
    event_result = await db.execute(
        select(ScheduleEvent).where(
            ScheduleEvent.id == event_id,
            ScheduleEvent.teacher_id == current_user.id,
        )
    )
    if not event_result.scalar_one_or_none():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    proposal = RescheduleProposal(
        event_id=event_id,
        proposed_by=current_user.id,
        new_start=datetime.fromisoformat(new_start),
        new_end=datetime.fromisoformat(new_end),
        status=ProposalStatus.PENDING,
    )
    db.add(proposal)
    await db.flush()
    await send_proposal_email(current_user, proposal)
    return templates.TemplateResponse(
        "components/inline_success.html",
        {"request": request, "message": "Propozycja przesłana do akceptacji."},
    )
```

- [ ] Add availability block endpoints to `app/api/routes_api.py`.
  First add these imports to the existing import block:
  ```python
  from datetime import datetime
  from app.models.availability import UnavailableBlock
  from app.models.users import User, UserRole
  from app.core.auth import require_teacher_or_admin
  ```
  Then add the endpoints:
```python
# Add these to the existing router

@router.get("/availability/{teacher_id}", response_model=list[dict])
async def get_availability_blocks(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return unavailable blocks for a teacher (for FullCalendar rendering)."""
    result = await db.execute(
        select(UnavailableBlock).where(UnavailableBlock.teacher_id == teacher_id)
    )
    return [
        {
            "id": str(b.id),
            "title": b.note or "Niedostępny",
            "start": b.start_time.isoformat(),
            "end": b.end_time.isoformat(),
            "color": "#6b7280",
            "display": "background",
        }
        for b in result.scalars().all()
    ]


@router.post("/availability", status_code=201)
async def create_availability_block(
    teacher_id: UUID = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    note: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
) -> dict:
    # Ownership check: teachers can only mark unavailability for themselves.
    if current_user.role != UserRole.ADMIN and current_user.id != teacher_id:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN)
    block = UnavailableBlock(
        teacher_id=teacher_id,
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time),
        note=note or None,
    )
    db.add(block)
    await db.flush()
    await db.refresh(block)
    return {"id": str(block.id)}
```

- [ ] Create `app/templates/teacher/dashboard.html` — upcoming sessions list. Dark theme. Shows: date, time, subject, student name, "Zaproponuj zmianę terminu" button per event.

- [ ] Create `app/templates/teacher/calendar.html` — FullCalendar, teacher-specific. Fetches only their events from `/api/events?teacher_id=X` and unavailable blocks from `/api/availability/X`. Has "Zaznacz niedostępność" button that opens a date/time form, submits to `/api/availability` via JS.

- [ ] Create `app/templates/teacher/proposals.html` — table of proposals with status badges (pending=yellow, approved=green, rejected=red).

- [ ] Update `/api/events` to accept optional `teacher_id` query param filter:
```python
@router.get("/events", response_model=list[ScheduleEventRead])
async def get_events(
    teacher_id: UUID | None = None,
    student_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleEventRead]:
    q = select(ScheduleEvent)
    if teacher_id:
        q = q.where(ScheduleEvent.teacher_id == teacher_id)
    if student_id:
        q = q.where(ScheduleEvent.student_id == student_id)
    result = await db.execute(q)
    return [ScheduleEventRead.model_validate(e) for e in result.scalars().all()]
```

- [ ] Commit:
```bash
git add app/api/routes_teacher.py app/api/routes_api.py app/templates/teacher/
git commit -m "feat(teacher): dashboard, calendar, unavailable blocks, reschedule proposals"
```

---

## Chunk 7: Student view + profile + email stubs + stats fix

### Task 10: Student dashboard

**Files:**
- Modify: `app/api/routes_student.py`
- Create: `app/templates/student/dashboard.html`

- [ ] Update `app/api/routes_student.py`:
```python
"""Student-facing HTML routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.auth import require_role
from app.core.templates import templates
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.users import User, UserRole

router = APIRouter(prefix="/student", tags=["student"])


@router.get("/", response_class=HTMLResponse)
async def student_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.STUDENT)),
) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduleEvent)
        .where(ScheduleEvent.student_id == current_user.id)
        .options(selectinload(ScheduleEvent.teacher), selectinload(ScheduleEvent.offering))
        .order_by(ScheduleEvent.start_time.desc())
    )
    events = result.scalars().all()
    upcoming = [e for e in events if e.start_time >= now and e.status == EventStatus.SCHEDULED]
    past = [e for e in events if e.start_time < now]
    return templates.TemplateResponse(
        "student/dashboard.html",
        {"request": request, "user": current_user, "upcoming": upcoming, "past": past},
    )
```

- [ ] Create `app/templates/student/dashboard.html` — read-only view. Two sections: "Nadchodzące zajęcia" and "Historia". Cream/light theme (extends base with override). Shows: date/time, subject, teacher name, status badge.

---

### Task 11: Profile — change own password

**Files:**
- Modify: `app/api/routes_profile.py`
- Create: `app/templates/profile.html`

- [ ] Update `app/api/routes_profile.py`:
```python
"""User profile routes — change own password."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.auth import require_auth
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
        "profile.html", {"request": request, "user": current_user}
    )


@router.post("/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> HTMLResponse:
    if not verify_password(old_password, current_user.hashed_password):
        return templates.TemplateResponse(
            "profile.html",
            {"request": request, "user": current_user, "error": "Nieprawidłowe obecne hasło."},
        )
    current_user.hashed_password = hash_password(new_password)
    await db.flush()
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": current_user, "success": "Hasło zmienione pomyślnie."},
    )
```

---

### Task 12: Email stubs + fix /api/stats

- [ ] Extend `app/services/email.py` with proposal notification stubs:
```python
async def send_proposal_email(teacher: "User", proposal: "RescheduleProposal") -> None:
    logger.info(
        "Reschedule proposal | teacher=%s | event_id=%s | new_start=%s",
        teacher.full_name, proposal.event_id, proposal.new_start,
    )

async def send_proposal_outcome_email(proposal: "RescheduleProposal", approved: bool) -> None:
    outcome = "approved" if approved else "rejected"
    logger.info(
        "Proposal outcome=%s | proposal_id=%s", outcome, proposal.id
    )
```

- [ ] Fix `/api/stats` — add `pending_proposals` count:
```python
from app.models.proposals import RescheduleProposal, ProposalStatus

# inside get_stats():
pending_proposals = (await db.execute(
    select(func.count(RescheduleProposal.id))
    .where(RescheduleProposal.status == ProposalStatus.PENDING)
)).scalar_one()

return {
    ...existing fields...,
    "pending_proposals": pending_proposals,
}
```

- [ ] Restart and verify `/api/stats` returns 200:
```bash
docker-compose exec web curl -s http://localhost:8000/api/stats | python -m json.tool
```

- [ ] Commit everything remaining:
```bash
git add app/api/routes_student.py app/api/routes_profile.py \
        app/api/routes_api.py app/services/email.py \
        app/templates/student/ app/templates/profile.html \
        app/templates/errors/
git commit -m "feat: student dashboard, profile password change, stats fix, email stubs"
```

---

## Chunk 8: Rebuild CSS + final wiring + PR

### Task 13: Rebuild Tailwind, run all tests, merge

- [ ] Rebuild CSS (new classes: `bg-navy`, `text-cream`, etc. used in new templates):
```bash
docker run --rm -v "$(pwd):/app:z" -w /app node:20-alpine \
  sh -c "npm install tailwindcss@3.4.0 && \
  ./node_modules/.bin/tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css"
```

- [ ] Run full test suite:
```bash
docker-compose exec web pytest tests/ -v
```
Expected: all PASSED

- [ ] Manual smoke test:
  - `http://localhost:8000/login` → login with admin credentials → `/admin/` with proposals badge
  - Login as teacher → `/teacher/` with upcoming sessions
  - Login as student → `/student/` with appointments
  - Admin `/admin/users` → table shows all 5 seeded users
  - Admin `/admin/proposals` → empty (no proposals yet)
  - Teacher calendar → shows own events + grey unavailability block

- [ ] Commit CSS:
```bash
git add app/static/css/style.css
git commit -m "chore: rebuild Tailwind CSS with new template classes"
```

- [ ] Push and open PR:
```bash
git push -u origin feature/auth-and-admin
# open PR via GitHub MCP
```

- [ ] After PR review: merge locally:
```bash
git checkout main && git merge feature/auth-and-admin && git push
git branch -d feature/auth-and-admin
git push origin --delete feature/auth-and-admin
```
