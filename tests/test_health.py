"""Tests for the /health liveness probe endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


async def test_health_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200


async def test_health_returns_status_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    data = r.json()
    assert data.get("status") == "ok"


async def test_health_response_is_json():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.headers["content-type"].startswith("application/json")
