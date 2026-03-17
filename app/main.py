"""FastAPI application entry-point for Ekorepetycje."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_landing, routes_api, routes_admin
from app.api import routes_auth, routes_profile, routes_teacher, routes_student
from app.core.auth import _LoginRedirect
from app.core.config import settings

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Ekorepetycje", debug=settings.DEBUG)

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


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — returns a simple status payload."""
    return {"status": "ok"}
