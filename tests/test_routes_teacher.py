"""Integration tests for /teacher/ HTML routes."""

import pytest


# ── Unauthenticated access ────────────────────────────────────────────────────

async def test_teacher_dashboard_unauthenticated_redirects_to_login(client):
    r = await client.get("/teacher/")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_teacher_calendar_unauthenticated_redirects_to_login(client):
    r = await client.get("/teacher/calendar")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_teacher_proposals_unauthenticated_redirects_to_login(client):
    r = await client.get("/teacher/proposals")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


# ── Authenticated as teacher ──────────────────────────────────────────────────

async def test_teacher_dashboard_authenticated_returns_200(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/teacher/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_teacher_calendar_authenticated_returns_200(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/teacher/calendar", cookies={"session": cookie})
    assert r.status_code == 200


async def test_teacher_proposals_authenticated_returns_200(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/teacher/proposals", cookies={"session": cookie})
    assert r.status_code == 200


# ── Wrong role: student accessing teacher routes ──────────────────────────────

async def test_teacher_dashboard_as_student_redirects_to_student(client, student_in_db):
    """Student has wrong role for /teacher/ → redirected to /student/."""
    _, cookie = student_in_db
    r = await client.get("/teacher/", cookies={"session": cookie})
    assert r.status_code == 303
    assert "/student/" in r.headers["location"]


# ── Note: /teacher/ uses require_teacher_OR_admin — so admin CAN access it ───

async def test_teacher_dashboard_as_admin_returns_200(client, admin_in_db):
    """Admin is allowed by require_teacher_or_admin — should get 200."""
    _, cookie = admin_in_db
    r = await client.get("/teacher/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_teacher_calendar_as_admin_returns_200(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/teacher/calendar", cookies={"session": cookie})
    assert r.status_code == 200
