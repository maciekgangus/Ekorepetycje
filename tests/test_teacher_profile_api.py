"""Tests for teacher photo upload and profile PATCH endpoints."""
import io
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image


def _make_jpeg_bytes() -> bytes:
    """Create a tiny valid JPEG image in memory."""
    img = Image.new("RGB", (10, 10), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def test_upload_photo_unauthenticated_returns_401_or_redirect(client: AsyncClient):
    r = await client.post(
        "/api/teachers/me/photo",
        files={"file": ("photo.jpg", _make_jpeg_bytes(), "image/jpeg")},
    )
    # Must not be 200 without auth
    assert r.status_code in (401, 403, 302, 303)


async def test_patch_profile_unauthenticated_returns_401_or_redirect(client: AsyncClient):
    r = await client.patch(
        "/api/teachers/me/profile",
        data={"bio": "Test bio", "specialties": "Matematyka"},
    )
    assert r.status_code in (401, 403, 302, 303)


async def test_upload_endpoint_exists_not_404(client: AsyncClient):
    """The upload endpoint must exist (not 404). Auth will fire before MIME check."""
    r = await client.post(
        "/api/teachers/me/photo",
        files={"file": ("malware.php", b"<?php echo 1; ?>", "image/jpeg")},
    )
    # Auth fires first → 401/403/redirect. Not 404 = endpoint is registered.
    assert r.status_code in (401, 403, 302, 303)
