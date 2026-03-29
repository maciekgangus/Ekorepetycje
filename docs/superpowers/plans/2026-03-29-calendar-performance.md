# Calendar Performance — Date-Range Lazy Loading + Redis Cache

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-table event dump with date-windowed queries, composite DB indexes, and a 5-minute Redis cache per user per window.

**Architecture:** FullCalendar already sends `?start=...&end=...` on every navigation; the backend just ignores them today. We add those params to `GET /api/events`, index `(teacher_id, start_time)` and `(student_id, start_time)`, wrap the endpoint in a Redis cache keyed by user+window, and invalidate on every event write. Admin calendar bypasses the cache.

**Tech Stack:** FastAPI, SQLAlchemy async, `redis[asyncio]`, APScheduler (unchanged), Alembic, Jinja2/HTMX (minimal JS change in admin_calendar.js).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `docker-compose.yml` | Modify | Add `redis:7-alpine` service + named volume |
| `requirements.txt` | Modify | Add `redis[asyncio]` |
| `app/core/config.py` | Modify | Add `REDIS_URL` setting |
| `app/core/cache.py` | Create | Thin async Redis wrapper (get/set/invalidate) |
| `alembic/versions/xxxx_add_event_time_indexes.py` | Create | Composite indexes on schedule_events |
| `app/api/routes_api.py` | Modify | `start`/`end` params on GET /api/events; cache get/set; invalidate on writes |
| `app/static/js/admin_calendar.js` | Modify | Pass `fetchInfo.startStr`/`endStr` to fetch |
| `tests/test_calendar_performance.py` | Create | Date filter + cache miss/hit/invalidate tests |

---

### Task 1: Add Redis to infrastructure

**Files:**
- Modify: `docker-compose.yml`
- Modify: `requirements.txt`
- Modify: `app/core/config.py`

- [ ] **Step 1: Add Redis service to docker-compose.yml**

Replace the `volumes:` block at the bottom with:

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
  ollama_data:
  redis_data:
```

And add `redis` to the `web` service `depends_on`:

```yaml
  web:
    ...
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```

- [ ] **Step 2: Add redis to requirements.txt**

Append to `requirements.txt`:
```
redis[asyncio]
```

- [ ] **Step 3: Add REDIS_URL to config**

In `app/core/config.py`, add after `RESEND_TO_EMAIL`:

```python
    # ── Redis (event cache) ───────────────────────────────────────────────────
    # Leave empty to disable caching (tests, local dev without Redis).
    REDIS_URL: str = ""
```

- [ ] **Step 4: Rebuild and verify Redis starts**

```bash
docker compose down && docker compose up -d --build
docker compose exec redis redis-cli ping
```
Expected output: `PONG`

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml requirements.txt app/core/config.py
git commit -m "feat(infra): add Redis service for event window cache"
```

---

### Task 2: Cache module

**Files:**
- Create: `app/core/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cache.py`:

```python
"""Tests for the Redis cache wrapper.

These tests run without a real Redis instance — REDIS_URL is unset in CI.
The cache module must gracefully no-op (never raise) when Redis is unavailable.
"""
import pytest
from unittest.mock import AsyncMock, patch


async def test_get_returns_none_without_redis():
    """Cache miss when REDIS_URL is empty."""
    from app.core.cache import get_events
    result = await get_events("events:t:abc:2026-03-24:2026-03-31")
    assert result is None


async def test_set_does_not_raise_without_redis():
    """set_events silently no-ops when Redis is unavailable."""
    from app.core.cache import set_events
    await set_events("events:t:abc:2026-03-24:2026-03-31", "[]")  # must not raise


async def test_invalidate_does_not_raise_without_redis():
    """invalidate_user silently no-ops when Redis is unavailable."""
    import uuid
    from app.core.cache import invalidate_user
    await invalidate_user(uuid.uuid4(), uuid.uuid4())  # must not raise


async def test_cache_key_helper():
    """build_key produces the expected format."""
    import uuid
    from app.core.cache import build_key
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    key = build_key("t", uid, "2026-03-24T00:00:00", "2026-03-31T00:00:00")
    assert key == "events:t:12345678-1234-5678-1234-567812345678:2026-03-24:2026-03-31"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec web pytest tests/test_cache.py -v
```
Expected: `ImportError` — `app.core.cache` does not exist yet.

- [ ] **Step 3: Create app/core/cache.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec web pytest tests/test_cache.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/core/cache.py tests/test_cache.py
git commit -m "feat(cache): add Redis event window cache module with graceful no-op"
```

---

### Task 3: DB indexes migration

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_add_event_time_indexes.py`

- [ ] **Step 1: Generate migration file**

```bash
docker compose exec web alembic revision -m "add_event_time_indexes"
```

Note the generated filename (e.g. `alembic/versions/xxxx_add_event_time_indexes.py`) and open it.

- [ ] **Step 2: Write the migration**

Replace the generated body with:

```python
"""add_event_time_indexes

Revision ID: <generated>
Revises: 698e615463d4
Create Date: 2026-03-29
"""
from alembic import op

revision = '<generated>'
down_revision = '698e615463d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_schedule_events_teacher_start',
        'schedule_events', ['teacher_id', 'start_time'],
    )
    op.create_index(
        'ix_schedule_events_student_start',
        'schedule_events', ['student_id', 'start_time'],
    )


def downgrade() -> None:
    op.drop_index('ix_schedule_events_student_start', table_name='schedule_events')
    op.drop_index('ix_schedule_events_teacher_start', table_name='schedule_events')
```

- [ ] **Step 3: Apply migration**

```bash
docker compose exec web alembic upgrade head
```
Expected: `Running upgrade 698e615463d4 -> <new_rev>, add_event_time_indexes`

- [ ] **Step 4: Verify indexes exist**

```bash
docker compose exec db psql -U postgres -d ekorepetycje -c "\d schedule_events" | grep ix_schedule
```
Expected: two index rows containing `ix_schedule_events_teacher_start` and `ix_schedule_events_student_start`.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): add composite indexes on schedule_events (teacher_id, start_time) and (student_id, start_time)"
```

---

### Task 4: Add date-range filter and cache to GET /api/events

**Files:**
- Modify: `app/api/routes_api.py` lines 37–50

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calendar_performance.py`:

```python
"""Tests for date-windowed event fetching."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.auth import sign_session
from app.core.config import settings


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool)


def _csrf(cookie: str) -> str:
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(settings.SECRET_KEY, salt="csrf").dumps(cookie)


@pytest.fixture
async def windowed_env():
    """Two events: one this week, one 6 weeks later. One teacher, one student."""
    from app.models.users import User, UserRole
    from app.models.offerings import Offering
    from app.models.scheduling import ScheduleEvent, EventStatus

    engine = _engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    teacher_id = uuid.uuid4()
    student_id = uuid.uuid4()
    offering_id = uuid.uuid4()
    event_near_id = uuid.uuid4()
    event_far_id = uuid.uuid4()

    now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    near_start = now + timedelta(days=1)
    far_start  = now + timedelta(weeks=6)

    async with factory() as s:
        s.add(User(id=teacher_id, role=UserRole.TEACHER,
                   email=f"perf-t-{teacher_id}@test.com", hashed_password="h",
                   full_name="Perf Teacher"))
        s.add(User(id=student_id, role=UserRole.STUDENT,
                   email=f"perf-s-{student_id}@test.com", hashed_password="h",
                   full_name="Perf Student"))
        await s.flush()
        s.add(Offering(id=offering_id, title="Perf Subject",
                       base_price_per_hour=100, teacher_id=teacher_id))
        await s.flush()
        s.add(ScheduleEvent(id=event_near_id, title="Near Event",
                            start_time=near_start, end_time=near_start + timedelta(hours=1),
                            offering_id=offering_id, teacher_id=teacher_id,
                            student_id=student_id, status=EventStatus.SCHEDULED))
        s.add(ScheduleEvent(id=event_far_id, title="Far Event",
                            start_time=far_start, end_time=far_start + timedelta(hours=1),
                            offering_id=offering_id, teacher_id=teacher_id,
                            student_id=student_id, status=EventStatus.SCHEDULED))
        await s.commit()

    teacher_cookie = sign_session({"user_id": str(teacher_id)})

    yield {
        "teacher_id": teacher_id,
        "student_id": student_id,
        "offering_id": offering_id,
        "event_near_id": event_near_id,
        "event_far_id": event_far_id,
        "near_start": near_start,
        "far_start": far_start,
        "teacher_cookie": teacher_cookie,
    }

    async with factory() as s:
        for model, pk in [
            (__import__('app.models.scheduling', fromlist=['ScheduleEvent']).ScheduleEvent, event_near_id),
            (__import__('app.models.scheduling', fromlist=['ScheduleEvent']).ScheduleEvent, event_far_id),
            (__import__('app.models.offerings', fromlist=['Offering']).Offering, offering_id),
        ]:
            obj = await s.get(model, pk)
            if obj: await s.delete(obj)
        await s.flush()
        for uid in (teacher_id, student_id):
            u = await s.get(__import__('app.models.users', fromlist=['User']).User, uid)
            if u: await s.delete(u)
        await s.commit()
    await engine.dispose()


async def test_events_without_window_returns_all(client: AsyncClient, windowed_env):
    """No start/end params → all events returned (backwards-compatible)."""
    env = windowed_env
    r = await client.get(f"/api/events?teacher_id={env['teacher_id']}")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) in ids


async def test_events_with_window_excludes_far_event(client: AsyncClient, windowed_env):
    """start/end window filters out the far event."""
    env = windowed_env
    start = (env["near_start"] - timedelta(days=1)).isoformat()
    end   = (env["near_start"] + timedelta(days=14)).isoformat()
    r = await client.get(
        f"/api/events?teacher_id={env['teacher_id']}&start={start}&end={end}"
    )
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) not in ids


async def test_events_by_student_with_window(client: AsyncClient, windowed_env):
    """student_id + window also filters correctly."""
    env = windowed_env
    start = (env["near_start"] - timedelta(days=1)).isoformat()
    end   = (env["near_start"] + timedelta(days=14)).isoformat()
    r = await client.get(
        f"/api/events?student_id={env['student_id']}&start={start}&end={end}"
    )
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert str(env["event_near_id"]) in ids
    assert str(env["event_far_id"]) not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec web pytest tests/test_calendar_performance.py -v
```
Expected: `test_events_with_window_excludes_far_event` and `test_events_by_student_with_window` FAIL (far event is returned because filter is not implemented yet).

- [ ] **Step 3: Update GET /api/events in routes_api.py**

Replace the existing `get_events` function (lines 37–50):

```python
@router.get("/events", response_model=list[ScheduleEventRead])
async def get_events(
    teacher_id: UUID | None = None,
    student_id: UUID | None = None,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleEventRead]:
    """Return schedule events for FullCalendar, optionally filtered by teacher/student and date window.

    When start and end are provided (FullCalendar sends them automatically), only events
    whose start_time falls within [start, end) are returned. Results for teacher/student
    calenders are cached in Redis for 5 minutes per user per window.
    Admin requests (no teacher_id / student_id filter, or explicit filter) bypass the cache.
    """
    from app.core.cache import build_key, get_events as cache_get, set_events as cache_set
    import json

    # ── Cache lookup (teacher or student single-user queries only) ───────────
    cache_key: str | None = None
    if start and end:
        if teacher_id and not student_id:
            cache_key = build_key("t", teacher_id, start.isoformat(), end.isoformat())
        elif student_id and not teacher_id:
            cache_key = build_key("s", student_id, start.isoformat(), end.isoformat())

    if cache_key:
        cached = await cache_get(cache_key)
        if cached is not None:
            return json.loads(cached)

    # ── DB query ─────────────────────────────────────────────────────────────
    q = select(ScheduleEvent)
    if teacher_id:
        q = q.where(ScheduleEvent.teacher_id == teacher_id)
    if student_id:
        q = q.where(ScheduleEvent.student_id == student_id)
    if start:
        q = q.where(ScheduleEvent.start_time >= start)
    if end:
        q = q.where(ScheduleEvent.start_time < end)

    result = await db.execute(q)
    data = [ScheduleEventRead.model_validate(e) for e in result.scalars().all()]

    # ── Cache store ───────────────────────────────────────────────────────────
    if cache_key:
        await cache_set(cache_key, json.dumps([d.model_dump(mode="json") for d in data]))

    return data
```

Also add `Query` and `datetime` to the imports at the top of the file if not already present. `datetime` is already imported. Add `Query` — check the existing import line:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
```

`Query` is already imported. No change needed there.

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec web pytest tests/test_calendar_performance.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes_api.py tests/test_calendar_performance.py
git commit -m "feat(api): add date-range filter and Redis cache to GET /api/events"
```

---

### Task 5: Invalidate cache on all event writes

**Files:**
- Modify: `app/api/routes_api.py` — POST/PATCH/DELETE events, POST/PATCH series

- [ ] **Step 1: Add invalidation helper import to routes_api.py**

At the top of `routes_api.py`, after the existing imports, add:

```python
from app.core.cache import invalidate_user as _cache_invalidate
```

- [ ] **Step 2: Add invalidation after POST /api/events (create_event)**

In the `create_event` function, after `await db.refresh(event)` and before `return`:

```python
    await _cache_invalidate(event.teacher_id, event.student_id)
    return ScheduleEventRead.model_validate(event)
```

- [ ] **Step 3: Add invalidation after PATCH /api/events/{id} (update_event)**

In `update_event`, after `await db.refresh(event)` and before `return`:

```python
    await _cache_invalidate(event.teacher_id, event.student_id)
    return ScheduleEventRead.model_validate(event)
```

- [ ] **Step 4: Add invalidation after DELETE /api/events/{id} (delete_event)**

In `delete_event`, after `await db.delete(event)` and before the implicit `return None` (end of function), add:

```python
    await _cache_invalidate(event.teacher_id, event.student_id)
    await db.flush()
```

(Note: the existing code has `await db.delete(event)` followed by nothing. Add the invalidation line right after the delete, keeping the existing flush if present, or adding one.)

Look at the current delete_event function and ensure it reads:

```python
@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
    _csrf: None = Depends(require_csrf),
) -> None:
    """Delete a single schedule event. Teachers can only delete their own events."""
    result = await db.execute(select(ScheduleEvent).where(ScheduleEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if current_user.role != UserRole.ADMIN and event.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your event")
    teacher_id = event.teacher_id
    student_id = event.student_id
    await db.delete(event)
    await db.flush()
    await _cache_invalidate(teacher_id, student_id)
```

- [ ] **Step 5: Add invalidation to create_series and update_series_from**

In `create_series`, at the very end before `return`:

```python
    await _cache_invalidate(payload.teacher_id, payload.student_id)
    return {"series_id": str(series_id), "events_created": len(events), "conflicts": conflicts}
```

In `update_series_from`, at the very end before `return`:

```python
    await _cache_invalidate(payload.teacher_id, payload.student_id)
    return {"series_id": str(series_id), "events_updated": len(new_events)}
```

In `delete_series` (find the endpoint that deletes a whole series) — add similarly after the delete flush.

- [ ] **Step 6: Run full test suite to confirm nothing broke**

```bash
docker compose exec web pytest tests/ -q
```
Expected: 161+ passed, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add app/api/routes_api.py
git commit -m "feat(api): invalidate Redis event cache on all event and series writes"
```

---

### Task 6: Fix admin calendar to pass date window

**Files:**
- Modify: `app/static/js/admin_calendar.js` lines 70–79

- [ ] **Step 1: Update the events fetch function**

In `admin_calendar.js`, find the `events:` function block and change the fetch line from:

```javascript
        events: function (fetchInfo, successCallback, failureCallback) {
            const params = new URLSearchParams();
            const sel = document.getElementById('fc-user-filter');
            if (sel && sel.value) {
                const [type, id] = sel.value.split(':');
                if (type === 'teacher') params.set('teacher_id', id);
                else if (type === 'student') params.set('student_id', id);
            }
            fetch('/api/events?' + params.toString())
```

to:

```javascript
        events: function (fetchInfo, successCallback, failureCallback) {
            const params = new URLSearchParams();
            const sel = document.getElementById('fc-user-filter');
            if (sel && sel.value) {
                const [type, id] = sel.value.split(':');
                if (type === 'teacher') params.set('teacher_id', id);
                else if (type === 'student') params.set('student_id', id);
            }
            params.set('start', fetchInfo.startStr);
            params.set('end', fetchInfo.endStr);
            fetch('/api/events?' + params.toString())
```

- [ ] **Step 2: Verify visually**

```bash
docker compose up -d
```

Open `http://localhost:8000/login`, log in as admin (admin@eko.pl / haslo123), go to `/admin/calendar`, open browser DevTools → Network tab. Navigate to next week. Confirm the `/api/events` request includes `start=` and `end=` query params and returns only events within that window.

- [ ] **Step 3: Commit**

```bash
git add app/static/js/admin_calendar.js
git commit -m "fix(admin): pass FullCalendar date window to /api/events fetch"
```

---

### Task 7: Run full suite and push

- [ ] **Step 1: Run full test suite**

```bash
docker compose exec web pytest tests/ -q
```
Expected: 161+ passed.

- [ ] **Step 2: Push**

```bash
git push origin main
```
