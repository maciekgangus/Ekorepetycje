# Design: Calendar Performance — Date-Range Lazy Loading + Redis Cache

**Date:** 2026-03-29
**Status:** Approved

## Problem

`GET /api/events` returns every event ever recorded for a user. FullCalendar sends `start`/`end` query params automatically but the backend ignores them. After several months of usage a teacher or student calendar will download hundreds or thousands of rows on every page load. There are also no DB indexes on `start_time`, so even a filtered query does a full table scan per user.

---

## Approach

Date-range filtering on the backend + composite DB indexes + Redis per-user window cache (5 min TTL). Admin calendar bypasses the cache entirely.

---

## Architecture

### 1. Infrastructure

- Add `redis:7-alpine` service to `docker-compose.yml` with a named volume.
- Add `redis[asyncio]` to `requirements.txt`.
- Add `REDIS_URL=redis://redis:6379/0` to `.env` and `app/core/config.py` settings (default empty string so tests and local dev without Redis work transparently).

### 2. DB — Alembic migration

Add two composite indexes to `schedule_events`:

```sql
CREATE INDEX ix_schedule_events_teacher_start ON schedule_events (teacher_id, start_time);
CREATE INDEX ix_schedule_events_student_start ON schedule_events (student_id, start_time);
```

These make per-user date-range queries O(log n) regardless of total table size.

### 3. Backend — `GET /api/events` changes

Add optional `start: datetime | None = Query(None)` and `end: datetime | None = Query(None)` parameters. When provided, filter:

```python
q = q.where(ScheduleEvent.start_time >= start, ScheduleEvent.start_time < end)
```

FullCalendar passes ISO-8601 strings; FastAPI parses them automatically.

**Admin path:** the admin calendar uses a JS function that builds its own fetch URL. Update it to append `fetchInfo.startStr` and `fetchInfo.endStr` as `start` and `end` params. Admin responses are **not** cached — no cache key written, no invalidation needed.

**Teacher/student path:** FullCalendar's `url:` source already appends `?start=...&end=...` to the URL. No JS changes required for teacher or student calendars.

### 4. Cache layer — `app/core/cache.py`

A thin async wrapper around the Redis client. Gracefully no-ops (returns `None` / does nothing) when `REDIS_URL` is unset or the connection fails — cache misses fall through to the DB transparently.

```
get_events(key: str) -> str | None
set_events(key: str, data: str, ttl: int = 300) -> None
invalidate_user(teacher_id: UUID, student_id: UUID | None) -> None
```

**Cache keys:**
- Teacher: `events:t:{teacher_id}:{start_date}:{end_date}`
- Student: `events:s:{student_id}:{start_date}:{end_date}`

`start_date` / `end_date` are the ISO date portion of the FullCalendar window (e.g., `2026-03-24` / `2026-04-04`).

**Invalidation pattern:** `invalidate_user` deletes `events:t:{teacher_id}:*` and `events:s:{student_id}:*` using Redis `SCAN` + `DEL`. Runs on every event write.

### 5. Invalidation trigger points

Every endpoint that mutates a `ScheduleEvent` calls `await invalidate_user(teacher_id, student_id)`:

- `POST /api/events`
- `PATCH /api/events/{id}`
- `DELETE /api/events/{id}`
- `POST /api/series` (invalidate for the series teacher + student)
- `PATCH /api/series/{id}/from/{event_id}` (same)
- `DELETE /api/series/{id}` (same)
- `PATCH /api/change-requests/{id}/accept` (Spec 2 — event times change on accept)

### 6. Cache request flow

```
GET /api/events?teacher_id=X&start=S&end=E
  → build key events:t:X:S:E
  → Redis GET → hit → return cached JSON (skip DB)
                miss → query Postgres
                      → Redis SET (TTL 5 min)
                      → return
```

---

## Error Handling

- Redis connection error on read → log warning, treat as cache miss, serve from DB.
- Redis connection error on write/invalidate → log warning, continue (stale cache acceptable for ≤5 min).
- Missing `start`/`end` params → no date filter applied (backwards-compatible; admin unfiltered view still works).

---

## Testing

- Existing tests are unaffected: `REDIS_URL` is not set in the test environment, so the cache module returns `None` on every `get_events` call and skips all `set_events`/`invalidate_user` calls silently.
- New integration tests:
  - `GET /api/events?teacher_id=X&start=S&end=E` returns only events within the window.
  - Events outside the window are excluded.
  - Cache hit path: second identical request returns same data without hitting DB (verified by mocking the DB layer or asserting Redis key exists).
  - Invalidation: after `DELETE /api/events/{id}`, the cache key for that teacher is gone.

---

## Files Touched

| File | Change |
|---|---|
| `docker-compose.yml` | Add `redis` service |
| `requirements.txt` | Add `redis[asyncio]` |
| `app/core/config.py` | Add `REDIS_URL` setting |
| `app/core/cache.py` | New — cache wrapper |
| `app/api/routes_api.py` | `start`/`end` params on `GET /api/events`; `invalidate_user` calls on all writes |
| `app/static/js/admin_calendar.js` | Pass `fetchInfo.startStr`/`endStr` to fetch |
| `alembic/versions/xxxx_add_event_time_indexes.py` | New migration |
| `tests/test_calendar_performance.py` | New tests |
