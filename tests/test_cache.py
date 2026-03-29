"""Tests for the Redis cache wrapper.

These tests run without a real Redis instance — REDIS_URL is unset in CI.
The cache module must gracefully no-op (never raise) when Redis is unavailable.
"""
import pytest


async def test_get_returns_none_without_redis():
    """Cache miss when REDIS_URL is empty."""
    from app.core.cache import get_events
    result = await get_events("events:t:abc:2026-03-24:2026-03-31")
    assert result is None


async def test_set_does_not_raise_without_redis():
    """set_events silently no-ops when Redis is unavailable."""
    from app.core.cache import set_events
    result = await set_events("events:t:abc:2026-03-24:2026-03-31", "[]")
    assert result is None


async def test_invalidate_does_not_raise_without_redis():
    """invalidate_user silently no-ops when Redis is unavailable."""
    import uuid
    from app.core.cache import invalidate_user
    result = await invalidate_user(uuid.uuid4(), uuid.uuid4())
    assert result is None


async def test_cache_key_helper():
    """build_key produces the expected format."""
    import uuid
    from app.core.cache import build_key
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = build_key("t", uid, "2026-03-24T00:00:00", "2026-03-31T00:00:00")
    assert key == "events:t:12345678-1234-5678-1234-567812345678:2026-03-24:2026-03-31"
