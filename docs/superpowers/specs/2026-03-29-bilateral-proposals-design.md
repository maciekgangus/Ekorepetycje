# Design: Bilateral Reschedule Proposals — Teacher ↔ Student Direct Approval

**Date:** 2026-03-29
**Status:** Approved

## Problem

The current reschedule proposal flow routes through the admin: a teacher proposes a new time, admin approves or rejects it. This creates unnecessary overhead — admin should not be a middleman in a bilateral teacher/student scheduling negotiation. Additionally, students have no way to propose a reschedule at all.

Admin should receive a passive notification badge (count of pending changes) but take no action.

---

## Approach

Drop the `RescheduleProposal` model and admin approval endpoints. Build a clean `EventChangeRequest` model with explicit proposer/responder semantics. Both teacher and student can initiate. The receiving party approves or rejects directly. On accept, the event times update automatically. Admin sees only a badge count.

---

## Architecture

### 1. New model — `EventChangeRequest`

**File:** `app/models/change_requests.py`

```
id:           UUID (PK)
event_id:     UUID (FK schedule_events.id, ON DELETE CASCADE)
proposer_id:  UUID (FK users.id)
responder_id: UUID (FK users.id)
new_start:    datetime (timezone-aware)
new_end:      datetime (timezone-aware)
note:         str | None   -- optional message from proposer
status:       Enum(PENDING, ACCEPTED, REJECTED, CANCELLED)
created_at:   datetime
resolved_at:  datetime | None
```

Relationships: `proposer`, `responder`, `event` (all lazy-loaded or selectinload as needed).

**Derivation rule:** `responder_id` is always set by the backend from `event.teacher_id` and `event.student_id` — it is the party that did NOT initiate the request. Frontend never sends `responder_id`.

### 2. Alembic migrations

Two sequential migrations (separate files, separate revision IDs):

1. `add_event_change_requests_table` — creates `event_change_requests` with all columns and indexes.
2. `drop_reschedule_proposals_table` — drops `reschedule_proposals`. Runs after the new system is verified.

Keeping them separate allows safe rollback: if migration 2 is reverted, the old table is restored.

### 3. Pydantic schemas — `app/schemas/change_requests.py`

```
EventChangeRequestCreate:
  event_id, new_start, new_end, note (optional)

EventChangeRequestRead:
  id, event_id, proposer_id, responder_id,
  new_start, new_end, note, status, created_at, resolved_at
  model_config from_attributes=True
```

### 4. API — `app/api/routes_change_requests.py`

All endpoints require `require_auth` (teacher or student). CSRF required on mutating endpoints.

| Method | Path | Who | Action |
|---|---|---|---|
| `POST` | `/api/change-requests` | Teacher or Student | Create request; derive responder; send email to responder; 422 if event has no student |
| `PATCH` | `/api/change-requests/{id}/accept` | Responder only | Update event times; stamp resolved_at; invalidate Redis; email proposer |
| `PATCH` | `/api/change-requests/{id}/reject` | Responder only | Set REJECTED; stamp resolved_at; email proposer |
| `PATCH` | `/api/change-requests/{id}/cancel` | Proposer only | Set CANCELLED if still PENDING |
| `GET` | `/api/change-requests/pending-count` | Any auth user | Returns `{"count": N}` — admin: all PENDING requests; teacher/student: only requests where they are proposer or responder |
| `GET` | `/api/change-requests` | Any auth user | Returns requests where user is proposer or responder (teacher/student); all requests for admin (read-only) |

**Authorization rules:**
- Accept/reject: `current_user.id == request.responder_id`, else 403.
- Cancel: `current_user.id == request.proposer_id` and `status == PENDING`, else 403.
- All reads: only requests involving `current_user` are returned.

**On accept:** update `event.start_time = request.new_start`, `event.end_time = request.new_end`, then call `await invalidate_user(event.teacher_id, event.student_id)` (Spec 1 cache invalidation).

### 5. Email service — `app/services/email.py`

Replace the two existing stubs with real HTML implementations:

- `send_change_request_email(request, event)` — sent to responder when request is created. Contains proposer name, event title, proposed new time, and a link to their proposals page.
- `send_change_request_outcome_email(request, event, accepted: bool)` — sent to proposer on accept or reject. Contains outcome, event title, and final time if accepted.

Both follow the same Resend / log-fallback pattern as existing emails. Both are `async` and called with `asyncio.to_thread` for the sync Resend SDK.

### 6. Admin changes

- Remove `GET /admin/proposals` route and template from `routes_admin.py`.
- Remove `POST /admin/proposals/{id}/approve` and `POST /admin/proposals/{id}/reject`.
- Remove `pending_proposals` context from admin dashboard, users, and proposals template responses.
- Remove `admin/proposals.html` template.
- Admin navbar badge: replace `pending_proposals` count with a call to the same `GET /api/change-requests/pending-count` endpoint (admin is a valid auth user). Badge is display-only — no action link.

### 7. Teacher UI

**Dashboard (`teacher/dashboard.html`):**
- "Zaproponuj zmianę" button on each event card opens an HTMX-powered inline form fragment (`components/change_request_form.html`) with datetime inputs and optional note field.
- Form POSTs to `/api/change-requests` via HTMX; on success shows "Wysłano prośbę o zmianę ✓"; on error shows inline error message.

**Proposals page (`teacher/proposals.html`):**
- Two sections: "Oczekujące na Twoją odpowiedź" (incoming — responder) and "Twoje wysłane prośby" (outgoing — proposer).
- Incoming: Accept / Reject buttons (HTMX PATCH → swap row with inline success/error).
- Outgoing: Cancel button if status=PENDING, else status badge.
- Navbar link "Propozycje" with badge count.

### 8. Student UI

**Dashboard (`student/dashboard.html`):**
- Add "Zaproponuj zmianę" button to each upcoming event card — same HTMX fragment as teacher.

**New proposals page (`student/proposals.html`):**
- Identical layout to teacher proposals page.
- Route: `GET /student/proposals` in `routes_student.py`.

**Student navbar (`components/navbar_student.html`):**
- Add "Propozycje" link with badge count (same HTMX polling pattern as teacher).

### 9. Navbar badge — both teacher and student

HTMX attribute on the badge `<span>`:
```html
hx-get="/api/change-requests/pending-count"
hx-trigger="load, every 60s"
hx-target="this"
hx-swap="innerHTML"
```
Returns plain integer text from a small inline template. No full-page reload needed.

---

## Migration Safety

1. New `event_change_requests` table is added first and fully tested before old code is removed.
2. Old `RescheduleProposal` Python model and routes are removed in the same PR as the new implementation — not before.
3. `reschedule_proposals` DB table is dropped in a second migration that runs last. If tests fail at any point, this migration can be rolled back independently without data loss.
4. All existing tests must pass after each migration step.

---

## Error Handling

- `POST /api/change-requests` with an event that has no `student_id` → 422 "Nie można zaproponować zmiany dla zajęć bez przypisanego ucznia."
- Accept/reject/cancel on a non-PENDING request → 409 "Prośba nie jest już oczekująca."
- Accept where new times overlap an existing event → 409 from `_assert_no_overlap` (reuses the double-booking guard from previous work).
- Email failures → logged as warnings, do not fail the HTTP response.

---

## Testing

- `POST /api/change-requests` — teacher creates request for own event → 201, email logged.
- `POST /api/change-requests` — student creates request → 201.
- `POST /api/change-requests` — wrong user (not teacher or student of that event) → 403.
- `POST /api/change-requests` — event has no student → 422.
- Accept by responder → 200, event times updated, request status=ACCEPTED.
- Accept by proposer (wrong party) → 403.
- Accept already-resolved request → 409.
- Accept that would create a double-booking → 409.
- Reject by responder → 200, status=REJECTED.
- Cancel by proposer → 200, status=CANCELLED.
- `GET /api/change-requests/pending-count` → returns correct count for current user.
- Admin cannot approve/reject (endpoints removed → 404).

---

## Files Touched

| File | Change |
|---|---|
| `app/models/change_requests.py` | New model |
| `app/schemas/change_requests.py` | New schemas |
| `app/api/routes_change_requests.py` | New routes |
| `app/main.py` | Register new router |
| `app/services/email.py` | Replace proposal stubs with real implementations |
| `app/api/routes_admin.py` | Remove proposals routes and pending_proposals context |
| `app/api/routes_student.py` | Add `/student/proposals` route |
| `app/api/routes_teacher.py` | Update proposals route to use new model |
| `app/templates/admin/proposals.html` | Delete |
| `app/templates/teacher/proposals.html` | Rewrite for new model |
| `app/templates/student/proposals.html` | New |
| `app/templates/components/change_request_form.html` | New HTMX fragment |
| `app/templates/components/navbar_student.html` | Add badge + proposals link |
| `app/templates/components/navbar_admin.html` | Replace pending_proposals badge |
| `app/templates/teacher/dashboard.html` | Add propose button + badge |
| `app/templates/student/dashboard.html` | Add propose button |
| `alembic/versions/xxxx_add_event_change_requests.py` | New migration |
| `alembic/versions/xxxx_drop_reschedule_proposals.py` | New migration |
| `tests/test_change_requests.py` | New tests |
