"""Integration tests for GET /api/stats.

The /api/stats endpoint has NO auth guard in routes_api.py — it is a public
JSON endpoint used to hydrate the admin dashboard widget. We test that it
returns 200 with the expected keys regardless of auth state, and that an
authenticated admin also gets a valid response.
"""

import pytest

EXPECTED_KEYS = {
    "total_events",
    "scheduled",
    "completed",
    "cancelled",
    "total_offerings",
    "total_teachers",
    "pending_proposals",
    "total_students",
    "lessons_this_week",
    "lessons_this_month",
    "lessons_last_month",
    "revenue_this_month",
    "revenue_last_month",
    "revenue_6mo_avg",
    "revenue_by_month",
    "teacher_stats",
}


async def test_get_stats_unauthenticated_returns_200(client):
    """GET /api/stats is public — no session cookie required."""
    r = await client.get("/api/stats")
    assert r.status_code == 200


async def test_get_stats_returns_expected_keys(client):
    r = await client.get("/api/stats")
    data = r.json()
    for key in EXPECTED_KEYS:
        assert key in data, f"Missing key: {key}"


async def test_get_stats_numeric_fields_are_non_negative(client):
    r = await client.get("/api/stats")
    data = r.json()
    for key in (
        "total_events", "scheduled", "completed", "cancelled",
        "total_offerings", "total_teachers", "total_students",
        "pending_proposals",
    ):
        assert data[key] >= 0, f"{key} should be >= 0"


async def test_get_stats_revenue_by_month_is_list(client):
    r = await client.get("/api/stats")
    assert isinstance(r.json()["revenue_by_month"], list)


async def test_get_stats_revenue_by_month_has_six_entries(client):
    """Should always return exactly 6 months of trend data."""
    r = await client.get("/api/stats")
    assert len(r.json()["revenue_by_month"]) == 6


async def test_get_stats_revenue_by_month_entry_shape(client):
    r = await client.get("/api/stats")
    entries = r.json()["revenue_by_month"]
    for entry in entries:
        assert "month" in entry
        assert "revenue" in entry
        assert "count" in entry


async def test_get_stats_teacher_stats_is_list(client):
    r = await client.get("/api/stats")
    assert isinstance(r.json()["teacher_stats"], list)


async def test_get_stats_authenticated_as_admin_also_returns_200(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/api/stats", cookies={"session": cookie})
    assert r.status_code == 200
    data = r.json()
    for key in EXPECTED_KEYS:
        assert key in data
