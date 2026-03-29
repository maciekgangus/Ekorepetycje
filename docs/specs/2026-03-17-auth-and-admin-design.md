# Auth & Admin Panel — Design Spec
**Date:** 2026-03-17
**Status:** Approved by user

---

## Overview

Multi-teacher tutoring platform. Add session-based authentication and role-differentiated dashboards for admin, teacher, and student roles.

---

## Section 1: Authentication & Sessions

- **Mechanism:** Signed cookie sessions via `itsdangerous.TimestampSigner`
- **Cookie:** `httpOnly`, `SameSite=Lax`, signed, stores `{"user_id": "<uuid>", "role": "<role>"}`
- **Login route:** `GET/POST /login` — Jinja2 form, HTMX submit
- **Logout:** `POST /logout` — clears cookie, redirects to `/login`
- **Password hashing:** `passlib[bcrypt]` (matches existing `hashed_password` field on `User`)
- **Route guards:** Three dependency functions injected into FastAPI routes:
  - `require_auth` — any logged-in user
  - `require_role(TEACHER)` — teacher or admin
  - `require_role(ADMIN)` — admin only
- **No model changes** — `User` already has `email`, `hashed_password`, `role`, `full_name`

---

## Section 2: Role-based Routing & Dashboards

### URL structure

```
/login                    public
/logout                   public
/profile                  any logged-in user (change own password)

/admin/                   admin dashboard (stats, pending proposals badge)
/admin/users              user management (create, edit role, reset password)
/admin/calendar           full calendar, all teachers, filterable
/admin/proposals          pending reschedule proposals list

/teacher/                 teacher dashboard (upcoming sessions)
/teacher/calendar         own calendar (add sessions, mark unavailable)
/teacher/proposals        sent proposals + their status

/student/                 student dashboard (own appointments, read-only)
```

### Post-login redirect by role
- Admin → `/admin/`
- Teacher → `/teacher/`
- Student → `/student/`

### Permission matrix

| Action                        | Admin | Teacher     | Student  |
|-------------------------------|-------|-------------|----------|
| View all teachers' calendars  | ✓     | ✗           | ✗        |
| View own calendar             | ✓     | ✓           | read-only|
| Create appointments           | ✓     | ✓ own only  | ✗        |
| Mark unavailable blocks       | ✓     | ✓ own only  | ✗        |
| Propose reschedule            | ✓ direct | ✓ pending approval | ✗ |
| Approve/reject proposals      | ✓     | ✗           | ✗        |
| Manage users                  | ✓     | ✗           | ✗        |

---

## Section 3: User Management & Reschedule Flow

### User management (`/admin/users`)
- Table: name, email, role, actions
- **Create account:** admin sets name, email, role, temporary password
- **Change role:** inline HTMX dropdown per row
- **Reset password:** admin sets new password for any user
- **Own password change** (`/profile`): requires old password confirmation

### New models required

**`UnavailableBlock`**
```
id          UUID PK
teacher_id  FK → users.id
start_time  DateTime(tz)
end_time    DateTime(tz)
note        Text nullable
```
Renders on FullCalendar as non-interactive grey blocks.

**`RescheduleProposal`**
```
id              UUID PK
event_id        FK → schedule_events.id
proposed_by     FK → users.id
new_start       DateTime(tz)
new_end         DateTime(tz)
status          Enum(pending, approved, rejected)
created_at      DateTime(tz) server_default=now
```

### Reschedule flow

```
Teacher calendar
  → clicks appointment → "Propose reschedule"
  → picks new date/time
  → RescheduleProposal created (status=pending)
  → email sent to admin
  → admin dashboard badge +1

Admin /admin/proposals
  → Approve → ScheduleEvent updated to new time, proposal status=approved
            → email sent to teacher (approved)
  → Reject  → proposal status=rejected, event unchanged
            → email sent to teacher (rejected)
```

### Notifications
- **Email:** extend existing `send_contact_email` service pattern
- **In-app badge:** add `pending_proposals` count to `/api/stats` response; navbar shows red dot when > 0

---

## Implementation order

1. `.gitignore` update (docs/, local files) ← done
2. Auth: `passlib` + `itsdangerous` deps, session middleware, login/logout routes, route guards
3. New models: `UnavailableBlock`, `RescheduleProposal` + Alembic migration
4. Admin views: users CRUD, calendar with filters, proposals list
5. Teacher views: own calendar, unavailable blocks, propose reschedule
6. Student view: read-only appointment list
7. Email notifications for proposals
8. Seed script for demo data
