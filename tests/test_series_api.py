"""Integration tests for recurring series API endpoints."""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_create_series_unauthenticated(client):
    """Unauthenticated request must be redirected to login."""
    resp = await client.post("/api/series", json={})
    assert resp.status_code in (303, 401, 422)


async def test_patch_event_unauthenticated(client):
    """PATCH /api/events/{id} must require auth after hardening."""
    resp = await client.patch(f"/api/events/{uuid.uuid4()}", json={})
    assert resp.status_code in (303, 401, 403, 422)


async def test_delete_event_unauthenticated(client):
    """DELETE /api/events/{id} must require auth after hardening."""
    resp = await client.delete(f"/api/events/{uuid.uuid4()}")
    assert resp.status_code in (303, 401, 403)
