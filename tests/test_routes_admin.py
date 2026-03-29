"""Integration tests for /admin/ HTML routes."""

import pytest


# ── Unauthenticated access ────────────────────────────────────────────────────

async def test_admin_dashboard_unauthenticated_redirects_to_login(client):
    r = await client.get("/admin/")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_admin_users_unauthenticated_redirects_to_login(client):
    r = await client.get("/admin/users")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_admin_calendar_unauthenticated_redirects_to_login(client):
    r = await client.get("/admin/calendar")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


# ── Authenticated as admin ────────────────────────────────────────────────────

async def test_admin_dashboard_authenticated_returns_200(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/admin/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_admin_dashboard_contains_dashboard(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/admin/", cookies={"session": cookie})
    assert "Dashboard" in r.text


async def test_admin_users_authenticated_returns_200(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/admin/users", cookies={"session": cookie})
    assert r.status_code == 200


async def test_admin_calendar_authenticated_returns_200(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/admin/calendar", cookies={"session": cookie})
    assert r.status_code == 200


# ── Wrong role: teacher accessing admin routes ────────────────────────────────

async def test_admin_dashboard_as_teacher_redirects_to_teacher(client, teacher_in_db_with_cookie):
    """Teacher has wrong role for require_admin → redirected to /teacher/."""
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/admin/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/teacher/" in r.headers["location"]


async def test_admin_users_as_teacher_redirects(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/admin/users", cookies={"session": cookie})
    assert r.status_code == 303


# ── Wrong role: student accessing admin routes ────────────────────────────────

async def test_admin_dashboard_as_student_redirects_to_student(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/admin/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/student/" in r.headers["location"]
