# Recurring Appointment Series — Design Spec
**Date:** 2026-03-18
**Status:** Approved

---

## Overview

Add the ability for admins and teachers to create recurring appointment series (weekly, biweekly, custom N-week intervals) on the Ekorepetycje tutoring platform. Each series generates individual `ScheduleEvent` rows up-front (flat pre-generation). Events in a series look identical to standalone events on the calendar.

---

## Data Model

### New table: `recurring_series`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `teacher_id` | UUID FK → users | nullable=False |
| `student_id` | UUID FK → users | nullable=True — can be assigned later |
| `offering_id` | UUID FK → offerings | nullable=False |
| `title` | String(255) | Copied to each generated event |
| `interval_weeks` | Integer | 1=weekly, 2=biweekly, N=custom |
| `day_slots` | JSONB | Array of `{day, hour, minute, duration_minutes}` — day 0=Mon…6=Sun |
| `end_date` | Date | nullable — mutually exclusive with end_count |
| `end_count` | Integer | nullable — mutually exclusive with end_date |
| `start_date` | Date | nullable=False — first calendar week anchor for generation loop |
| `created_at` | DateTime(timezone=True) | server_default=now() |

### Modified table: `schedule_events`

Add one nullable column:

| Column | Type | Notes |
|---|---|---|
| `series_id` | UUID FK → recurring_series | nullable=True — null for standalone events |

### Generation logic

Walk forward from `start_date` week-by-week (step = `interval_weeks` weeks). For each step, expand every `day_slot` into a concrete `datetime` by combining the current week's Monday + `day` offset + `hour`/`minute`. Create one `ScheduleEvent` per slot. Stop when:
- `end_date` is set and the next occurrence would exceed it, OR
- `end_count` is set and that many events have been created.

Hard cap: 200 events per series creation. Return HTTP 422 if the rule would exceed this.

---

## API Endpoints

All new endpoints live in `app/api/routes_api.py`.

### `POST /api/series`
Create a series and generate all events.

**Auth:** Teacher (`teacher_id` must equal `current_user.id`) or Admin (any `teacher_id`).

**Request body:**
```json
{
  "teacher_id": "uuid",
  "student_id": "uuid | null",
  "offering_id": "uuid",
  "title": "string",
  "start_date": "2026-04-07",
  "interval_weeks": 1,
  "day_slots": [
    {"day": 0, "hour": 17, "minute": 0, "duration_minutes": 60},
    {"day": 3, "hour": 18, "minute": 30, "duration_minutes": 45}
  ],
  "end_date": "2026-06-30 | null",
  "end_count": null
}
```

**Validation:**
- Exactly one of `end_date` / `end_count` must be set.
- At least one `day_slot` required.
- `interval_weeks >= 1`.
- Generated event count must not exceed 200.

**Response:** `{"series_id": "uuid", "events_created": N}`

---

### `GET /api/series/{series_id}`
Returns the series rule for pre-filling the edit form.

**Auth:** Teacher (own series only) or Admin.

---

### `DELETE /api/series/{series_id}/from/{event_id}`
Deletes the given event and all future events in the series (ordered by `start_time`). If the deleted event is the first in the series, also deletes the `recurring_series` row.

**Auth:** Teacher (own series only) or Admin.

---

### `PATCH /api/series/{series_id}/from/{event_id}`
Updates the series from a given event forward. Deletes the given event and all following events, then re-generates from the new rule. Re-generation starts from the **ISO week** containing the deleted event's original `start_time` — the first generated occurrence is the earliest slot in `day_slots` that falls within that week or later. Past events are untouched.

**Auth:** Teacher (own series only) or Admin.

**Request body:** Same shape as `POST /api/series` (updated rule fields).

---

### Unchanged endpoints (with security hardening required)
- `DELETE /api/events/{event_id}` — delete a single event (standalone or series occurrence)
- `PATCH /api/events/{event_id}` — edit a single event (standalone or "this only" for series)

> **Security note:** Both endpoints currently have no auth dependency in `routes_api.py`. As part of this implementation pass, add `require_teacher_or_admin` + ownership check (`current_user.role == ADMIN or event.teacher_id == current_user.id`) to both endpoints for consistency with the new series endpoints.

---

## UI

### Admin calendar (`/admin/calendar`) and Teacher calendar (`/teacher/calendar`)

Both get a **"New Series" button** in the FullCalendar toolbar. Clicking it opens a **slide-in panel** (right side) with two sections:

**Section 1 — Details:**
- Teacher dropdown (admin only; hidden + prefilled for teachers)
- Student dropdown (optional)
- Offering dropdown
- Title (text input, auto-filled from offering selection, editable)

**Section 2 — Recurrence rule:**
- Interval: segmented control — `Weekly | Biweekly | Custom (N weeks)`
- Day slots: dynamic list, each row = `[Day ▼] [Start time] [Duration (min)] [× remove]` with an "Add slot" button
- End: radio — `End date [date picker]` OR `Number of sessions [number input]`
- Preview: live "Will create X sessions" count (computed in JS from rule)

**Submit** → `POST /api/series` → closes panel, refreshes FullCalendar.

---

### Context menu on recurring events

On hover over a calendar event that has a `series_id`, show a small `⋮` icon. Clicking it opens a context menu:

| Action | Endpoint |
|---|---|
| Edit this only | existing `PATCH /api/events/{id}` (inline modal) |
| Edit this & following | `PATCH /api/series/{series_id}/from/{event_id}` |
| Delete this only | existing `DELETE /api/events/{id}` |
| Delete this & following | `DELETE /api/series/{series_id}/from/{event_id}` |

To support the context menu, `GET /api/events` response must include `series_id` on each event (add to `ScheduleEventRead` schema).

---

## Edge Cases

| Case | Handling |
|---|---|
| No student at series creation | `student_id=null` on all events; assign per-event later via `PATCH /api/events/{id}` |
| All events individually deleted | Orphaned `recurring_series` row stays; harmless, no cleanup needed for MVP |
| Rule would generate > 200 events | HTTP 422 with message |
| Exactly one of end_date/end_count must be set | HTTP 422 with message |
| No day_slots | HTTP 422 with message |
| Teacher tries to create series for another teacher | HTTP 403 |
| Double-booking | Not checked (MVP) |

---

## File Map

| File | Change |
|---|---|
| `app/models/series.py` (new file) | New `RecurringSeries` ORM model. Do NOT modify `app/models/availability.py` (it contains `UnavailableBlock`) |
| `app/models/scheduling.py` | Add `series_id` FK column to `ScheduleEvent` |
| `app/models/__init__.py` | Import `RecurringSeries` |
| `app/db/base.py` | Import `RecurringSeries` here — this is the Alembic autogenerate discovery file. Also add missing imports for `UnavailableBlock` and `RescheduleProposal` (currently absent, which means future autogenerate migrations would miss changes to those models) |
| `app/schemas/series.py` | Pydantic schemas: `RecurringSeriesCreate`, `RecurringSeriesRead`, `DaySlot` |
| `app/schemas/scheduling.py` | Add `series_id` field to `ScheduleEventRead` |
| `app/api/routes_api.py` | Add series endpoints |
| `alembic/versions/` | New migration: add `recurring_series` table + `series_id` FK on `schedule_events` |
| `app/static/js/admin_calendar.js` | "New Series" button, slide-in panel, context menu |
| `app/static/js/teacher_calendar.js` | Same (new file or extract shared logic) |
| `app/templates/admin/calendar.html` | Include panel HTML |
| `app/templates/teacher/calendar.html` | Include panel HTML |
| `app/templates/components/series_panel.html` | Reusable HTMX/HTML panel fragment |
