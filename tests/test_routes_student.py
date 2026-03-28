"""Integration tests for /student/ HTML routes."""

import pytest


# ── Unauthenticated access ────────────────────────────────────────────────────

async def test_student_dashboard_unauthenticated_redirects_to_login(client):
    r = await client.get("/student/")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_student_calendar_unauthenticated_redirects_to_login(client):
    r = await client.get("/student/calendar")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


# ── Authenticated as student ──────────────────────────────────────────────────

async def test_student_dashboard_authenticated_returns_200(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/student/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_student_dashboard_contains_moje_zajecia(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/student/", cookies={"session": cookie})
    assert "Moje zajęcia" in r.text


async def test_student_calendar_authenticated_returns_200(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/student/calendar", cookies={"session": cookie})
    assert r.status_code == 200


async def test_student_calendar_contains_moj_kalendarz(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/student/calendar", cookies={"session": cookie})
    assert "Mój Kalendarz" in r.text


# ── Wrong role: admin accessing student routes ────────────────────────────────

async def test_student_dashboard_as_admin_redirects_to_admin(client, admin_in_db):
    """Admin has wrong role for /student/ → redirected to /admin/."""
    _, cookie = admin_in_db
    r = await client.get("/student/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/admin/" in r.headers["location"]


# ── Wrong role: teacher accessing student routes ──────────────────────────────

async def test_student_dashboard_as_teacher_redirects_to_teacher(client, teacher_in_db_with_cookie):
    """Teacher has wrong role for /student/ → redirected to /teacher/."""
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/student/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/teacher/" in r.headers["location"]
