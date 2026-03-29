"""Async Redis wrapper for FullCalendar event window caching.

All public functions silently no-op when REDIS_URL is unset or the Redis
connection fails — cache misses fall through to the database transparently.
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_client = None   # redis.asyncio.Redis | None — lazily initialised


def _get_client():
    """Return a shared Redis client, or None if REDIS_URL is not configured."""
    global _client
    if _client is not None:
        return _client
    from app.core.config import settings
    if not settings.REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis init failed: %s", exc)
    return _client


def build_key(role: str, user_id: UUID, start: str, end: str) -> str:
    """Build a cache key from role prefix, user UUID, and ISO date window.

    role:  't' for teacher, 's' for student
    start/end: ISO-8601 strings from FullCalendar (e.g. '2026-03-24T00:00:00+01:00')
    Only the date portion is used so timezone variants of the same window hit the same key.
    """
    start_date = start[:10]
    end_date = end[:10]
    return f"events:{role}:{user_id}:{start_date}:{end_date}"


async def get_events(key: str) -> str | None:
    """Return cached JSON string for key, or None on miss / error."""
    client = _get_client()
    if client is None:
        return None
    try:
        return await client.get(key)
    except Exception as exc:
        logger.warning("Redis GET error for %s: %s", key, exc)
        return None


async def set_events(key: str, data: str, ttl: int = 300) -> None:
    """Store JSON string under key with TTL seconds. Silently no-ops on error."""
    client = _get_client()
    if client is None:
        return
    try:
        await client.set(key, data, ex=ttl)
    except Exception as exc:
        logger.warning("Redis SET error for %s: %s", key, exc)


async def invalidate_user(teacher_id: UUID | None, student_id: UUID | None) -> None:
    """Delete all cached windows for a teacher and/or student.

    Uses SCAN to find matching keys and DEL to remove them.
    Silently no-ops when Redis is unavailable.
    """
    client = _get_client()
    if client is None:
        return
    patterns = []
    if teacher_id:
        patterns.append(f"events:t:{teacher_id}:*")
    if student_id:
        patterns.append(f"events:s:{student_id}:*")
    try:
        for pattern in patterns:
            async for key in client.scan_iter(pattern):
                await client.delete(key)
    except Exception as exc:
        logger.warning("Redis invalidate error: %s", exc)
