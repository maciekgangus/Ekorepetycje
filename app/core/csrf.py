"""CSRF protection — double-submit via session-bound token."""
from __future__ import annotations

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer

from app.core.config import settings

_signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")


def get_csrf_token(request: Request) -> str:
    """Return a CSRF token derived from the signed session cookie.

    The token is deterministic per session — no server-side storage needed.
    Returns an empty string for unauthenticated requests (no session cookie).
    """
    session = request.cookies.get("session", "")
    if not session:
        return ""
    return _signer.dumps(session)


def _verify(token: str, request: Request) -> bool:
    try:
        seed = _signer.loads(token)
        return seed == request.cookies.get("session", "")
    except BadSignature:
        return False


async def require_csrf(request: Request) -> None:
    """FastAPI dependency: reject state-changing requests with invalid/missing CSRF token.

    Safe methods (GET, HEAD, OPTIONS) and unauthenticated requests are skipped —
    auth guards on each endpoint will handle them separately.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    # No session → no CSRF needed (auth dependency will reject the request anyway)
    if not request.cookies.get("session"):
        return

    # 1. Check header (sent by HTMX via htmx:configRequest and by fetch() helpers)
    token = request.headers.get("X-CSRF-Token")

    # 2. Fall back to form field (plain <form> submissions without HTMX)
    if not token:
        try:
            form = await request.form()
            token = form.get("csrf_token")
        except Exception:
            pass

    if not token or not _verify(token, request):
        raise HTTPException(status_code=403, detail="CSRF token invalid or missing")
