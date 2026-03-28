"""FastAPI application entry-point for Ekorepetycje."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import routes_landing, routes_api, routes_admin
from app.api import routes_auth, routes_profile, routes_teacher, routes_student
from app.core.auth import _LoginRedirect, _WrongRole, _ROLE_HOME
from app.core.config import settings
from app.core.templates import templates
from app.core.limiter import limiter
from app.core.scheduler import scheduler, setup_scheduler

# ---------------------------------------------------------------------------
# Lifespan — start/stop background scheduler
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Ekorepetycje", debug=settings.DEBUG, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(routes_auth.router)
app.include_router(routes_profile.router)
app.include_router(routes_teacher.router)
app.include_router(routes_student.router)
app.include_router(routes_landing.router)
app.include_router(routes_api.router)
app.include_router(routes_admin.router)


@app.exception_handler(_LoginRedirect)
async def login_redirect_handler(request: Request, exc: _LoginRedirect) -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(_WrongRole)
async def wrong_role_handler(request: Request, exc: _WrongRole) -> RedirectResponse:
    # Send the user to their own dashboard instead of a 403 dead-end.
    return RedirectResponse(_ROLE_HOME.get(exc.role, "/"), status_code=303)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: Exception) -> HTMLResponse:
    return templates.TemplateResponse(request, "errors/403.html", status_code=403)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — returns a simple status payload."""
    return {"status": "ok"}
