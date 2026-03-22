# pytest-asyncio is configured via pytest.ini (asyncio_mode = auto).
# Shared fixtures and app-level dependency overrides.

import pytest
from typing import AsyncGenerator
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
