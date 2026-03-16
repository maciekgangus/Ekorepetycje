"""FastAPI application entry-point for Ekorepetycje."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes_landing
from app.core.config import settings

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Ekorepetycje", debug=settings.DEBUG)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(routes_landing.router)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — returns a simple status payload."""
    return {"status": "ok"}
