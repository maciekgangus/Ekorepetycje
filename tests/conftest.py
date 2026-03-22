# pytest-asyncio is configured via pytest.ini (asyncio_mode = auto).
# Shared fixtures and app-level dependency overrides.

import pytest
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.api.dependencies import get_db
from app.main import app


def _make_null_pool_engine():
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


@pytest.fixture(autouse=True)
async def override_get_db():
    """Replace get_db with a NullPool-backed session for every test.

    NullPool prevents asyncpg connections from being reused across event-loop
    boundaries (which causes 'another operation is in progress' errors when
    multiple async tests share the same SQLAlchemy engine).

    Note: the session commits on success (mirroring the production session
    middleware). This provides connection-level isolation but NOT data-level
    isolation — writes from one test persist to the shared test DB. Write
    tests should either clean up after themselves or seed data via a fixture
    that rolls back.
    """
    engine = _make_null_pool_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db_override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Shared ASGI test client — avoids repeating transport boilerplate in every test."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def teacher_in_db():
    """Insert a minimal TEACHER row, yield its UUID, then delete it.

    Used by tests that need a real teacher to exist in the DB (e.g. profile page 200 path).
    Manages its own engine + session so the row persists across the test's HTTP requests
    (which each get their own session from override_get_db).
    """
    import uuid as _uuid
    from app.models.users import User, UserRole

    engine = _make_null_pool_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_id = _uuid.uuid4()
    async with session_factory() as session:
        session.add(User(
            id=teacher_id,
            role=UserRole.TEACHER,
            email=f"test-teacher-{teacher_id}@example.com",
            hashed_password="hashed",
            full_name="Test Nauczyciel",
        ))
        await session.commit()

    yield teacher_id

    async with session_factory() as session:
        teacher = await session.get(User, teacher_id)
        if teacher:
            await session.delete(teacher)
            await session.commit()
    await engine.dispose()
