# Design: Role Lock, Offer Scoping, Student/Teacher QA

**Date:** 2026-03-29
**Status:** Approved

## Problem Summary

Three independent defects in the admin panel and data model:

1. **Role mutability** — admin can freely change any user's role (student ↔ teacher ↔ admin). Roles should be set at creation and frozen thereafter.
2. **Cross-teacher offer assignment** — `GET /api/offerings` returns all offerings regardless of teacher. The series panel caches them globally, allowing admin to assign Teacher B's offering to Teacher A's session. No backend validation enforces offer ownership on write.
3. **Student/teacher subpage QA** — student dashboard, student calendar, teacher dashboard, teacher calendar, proposals, and password change have not been manually verified end-to-end after recent theme changes.

---

## Workstream A: Remove Role Change

**Files:** `app/templates/admin/users.html`, `app/api/routes_admin.py`

- Remove the role-change `<form>` block (lines 82–91 in `users.html`) — keep the display badge.
- Remove or replace `POST /admin/users/{user_id}/role` endpoint with HTTP 405 / 410.
- Role is still set correctly at user creation time (the create-form `<select>` stays).

**Acceptance:** No role-change UI in the users table. Endpoint returns non-2xx. Existing tests pass.

---

## Workstream B: Offer-Teacher Scope

**Files:** `app/api/routes_api.py`, `app/static/js/series_panel.js`, `app/schemas/offerings.py`

### API layer
- Add optional `teacher_id: UUID | None = Query(None)` to `GET /api/offerings`.
- Filter query: `where(Offering.teacher_id == teacher_id)` when param is present.
- Ensure `OfferingRead` schema includes `teacher_id` field.

### Backend validation (series create + update)
- On `POST /api/series` and `PATCH /api/series/{id}/from/{event_id}`: after resolving the offering, assert `offering.teacher_id == payload.teacher_id`. Return 422 if mismatch.

### Frontend (series_panel.js)
- **Admin flow:** When teacher dropdown changes → clear offering dropdown + `_offerings = []` cache → re-fetch `/api/offerings?teacher_id=<selected>`.
- **Teacher (non-admin) flow:** On panel init, fetch `/api/offerings?teacher_id=<userId>` instead of unfiltered.
- Wire teacher `<select>` `onchange` to a new `spOnTeacherChange()` helper.

**Acceptance:** Offering dropdown only shows offerings belonging to the selected teacher. Submitting a mismatched offering_id via API returns 422.

---

## Workstream C: Student/Teacher QA

**Scope:** Automated + manual verification of all student/teacher subpages.

- Run full pytest suite inside Docker, confirm 158 passed.
- Log in as `marek@student.pl` / `haslo123`: verify dashboard loads (events list), calendar renders (FullCalendar visible), password change works.
- Log in as teacher: verify dashboard (upcoming events), calendar (FullCalendar, unavailability panel), proposals page.
- Fix any broken UI, missing data, or runtime errors found.
- Update or add tests for any gap discovered.

**Acceptance:** All pages return 200 with visible content, no JS console errors on load, password change succeeds, 158+ tests pass.

---

## Execution

Three independent git worktrees, one agent per workstream, running in parallel:

| Branch | Worktree |
|---|---|
| `fix/remove-role-change` | `/tmp/wt-role` |
| `fix/offer-teacher-scope` | `/tmp/wt-offers` |
| `qa/student-teacher-pages` | `/tmp/wt-qa` |

Each agent commits to its branch, then merges to `main` sequentially after the others finish to avoid conflicts.
