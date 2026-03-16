"""FastAPI application entry-point for Ekorepetycje."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Directory scaffolding (ensures paths exist even on a fresh clone)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

for directory in (
    STATIC_DIR / "css",
    STATIC_DIR / "js",
    STATIC_DIR / "img",
    TEMPLATES_DIR / "components",
    TEMPLATES_DIR / "landing",
    TEMPLATES_DIR / "admin",
):
    directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = FastAPI(title="Ekorepetycje")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    """Liveness probe — returns a simple status payload."""
    return {"status": "ok"}
