"""Integration tests for /profile routes."""

import pytest

from app.core.security import hash_password
from app.core.config import settings


def _csrf_token_for(session_cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    signer = URLSafeSerializer(settings.SECRET_KEY, salt="csrf")
    return signer.dumps(session_cookie)


# ── Unauthenticated access ────────────────────────────────────────────────────

async def test_profile_page_unauthenticated_redirects_to_login(client):
    r = await client.get("/profile/")
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


# ── Authenticated access ──────────────────────────────────────────────────────

async def test_profile_page_authenticated_returns_200(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/profile/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_profile_page_contains_change_password_text(client, teacher_in_db_with_cookie):
    _, cookie = teacher_in_db_with_cookie
    r = await client.get("/profile/", cookies={"session": cookie})
    assert "Zmień hasło" in r.text


async def test_profile_page_available_to_admin(client, admin_in_db):
    _, cookie = admin_in_db
    r = await client.get("/profile/", cookies={"session": cookie})
    assert r.status_code == 200


async def test_profile_page_available_to_student(client, student_in_db):
    _, cookie = student_in_db
    r = await client.get("/profile/", cookies={"session": cookie})
    assert r.status_code == 200


# ── POST /profile/password ────────────────────────────────────────────────────

async def test_change_password_wrong_old_password_returns_error(client, teacher_in_db_with_cookie):
    """Submitting the wrong old password returns 200 with an error message in HTML.

    The teacher fixture stores hashed_password='hashed' (not a real bcrypt hash), so
    we patch it to a real bcrypt hash first, then submit the wrong old password.
    """
    import uuid as _uuid
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.models.users import User

    teacher_id, cookie = teacher_in_db_with_cookie
    real_hash = hash_password("CorrectPassword!")

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        u = await s.get(User, teacher_id)
        if u:
            u.hashed_password = real_hash
            await s.commit()
    await engine.dispose()

    csrf = _csrf_token_for(cookie)
    r = await client.post(
        "/profile/password",
        data={
            "old_password": "definitely-wrong-password",
            "new_password": "newSecret123",
        },
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    # Returns the profile template with an error (200), not a redirect
    assert r.status_code == 200
    assert "Nieprawidłowe" in r.text


async def test_change_password_unauthenticated_redirects(client):
    r = await client.post(
        "/profile/password",
        data={"old_password": "x", "new_password": "y"},
    )
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_change_password_correct_old_password_shows_success(client, admin_in_db):
    """Admin user created with hashed_password='hashed'.
    We update it to a real bcrypt hash, then test the successful change path.
    """
    import uuid as _uuid
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.models.users import User

    admin_id, cookie = admin_in_db
    real_password = "OldPass123!"
    real_hash = hash_password(real_password)

    # Patch the hashed_password to a real bcrypt hash
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        u = await s.get(User, admin_id)
        if u:
            u.hashed_password = real_hash
            await s.commit()
    await engine.dispose()

    csrf = _csrf_token_for(cookie)
    r = await client.post(
        "/profile/password",
        data={"old_password": real_password, "new_password": "NewPass456!"},
        cookies={"session": cookie},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert "Hasło zmienione" in r.text
