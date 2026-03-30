# Ekorepetycje — Technical Documentation

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Directory Structure](#3-directory-structure)
4. [Database Schema](#4-database-schema)
5. [Authentication & Authorization](#5-authentication--authorization)
6. [Routes & Endpoints](#6-routes--endpoints)
7. [Business Logic & Services](#7-business-logic--services)
8. [Frontend Architecture](#8-frontend-architecture)
9. [Running Locally](#9-running-locally)
10. [Testing](#10-testing)
11. [AWS Deployment Guide](#11-aws-deployment-guide)

---

## 1. Project Overview

Ekorepetycje is a tutoring platform MVP built for a Polish market. It handles:

- **Public landing page** — marketing content, featured teachers, subject pages, contact form, AI chat widget
- **Teacher management** — profiles with photos, bio, specialties
- **Admin dashboard** — user CRUD, role management, offering creation, full calendar oversight
- **Teacher dashboard** — upcoming sessions, calendar, bilateral reschedule proposals
- **Student dashboard** — session calendar, bilateral reschedule proposals
- **Scheduling system** — one-off events and recurring series with conflict detection
- **Availability management** — single and recurring unavailability blocks
- **Redis caching** — event window query cache with graceful no-op fallback

The application is a server-rendered web app using HTMX for dynamic interactions. There is no client-side JavaScript framework — all interactivity is done via HTML fragments returned from the server, with the exception of FullCalendar (plain JS).

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI (Python 3.11) |
| ORM | SQLAlchemy (async) |
| Database | PostgreSQL 15 |
| Cache | Redis 7 (optional — graceful no-op if `REDIS_URL` unset) |
| Migrations | Alembic (async runner) |
| ASGI server | Uvicorn |
| Templates | Jinja2 |
| Interactivity | HTMX 1.9 |
| Styling | Tailwind CSS v3.4 |
| Calendar UI | FullCalendar v6 (loaded via CDN) |
| Charts | Chart.js v4 (loaded via CDN) |
| Auth | itsdangerous (signed cookies, 14-day session) |
| Password hashing | passlib + bcrypt |
| Image processing | Pillow |
| Validation | Pydantic v2 + pydantic-settings |
| Async DB driver | asyncpg |
| HTTP client | httpx (Turnstile verification, Ollama streaming) |
| AI chat (dev) | Ollama (local CPU LLM, `--profile ai`) |
| AI chat (prod) | Amazon Bedrock (boto3, IAM instance role) |
| Email | Resend API (falls back to logging if key unset) |
| CAPTCHA | Cloudflare Turnstile |
| Testing | pytest + pytest-asyncio + httpx |
| Container | Docker + Docker Compose |

---

## 3. Directory Structure

```
Ekorepetycje/
├── app/
│   ├── main.py                    # FastAPI app factory, router mounts, /health
│   ├── api/
│   │   ├── routes_landing.py      # Public HTML pages (Jinja2)
│   │   ├── routes_auth.py         # Login / logout
│   │   ├── routes_admin.py        # Admin dashboard HTML
│   │   ├── routes_teacher.py      # Teacher dashboard HTML
│   │   ├── routes_student.py      # Student dashboard HTML
│   │   ├── routes_profile.py      # Logged-in user profile page
│   │   ├── routes_change_requests.py  # Bilateral proposal JSON API
│   │   ├── routes_api.py          # JSON API (FullCalendar, series, teacher photos, stats)
│   │   └── dependencies.py        # get_db() session provider
│   ├── core/
│   │   ├── config.py              # Settings (DATABASE_URL, SECRET_KEY, LLM_PROVIDER, …)
│   │   ├── security.py            # hash_password, verify_password
│   │   ├── auth.py                # Session signing, require_* dependencies
│   │   ├── cache.py               # Async Redis wrapper; no-op when REDIS_URL=""
│   │   └── templates.py           # Jinja2Templates instance
│   ├── db/
│   │   ├── database.py            # AsyncEngine, AsyncSessionLocal, Base
│   │   └── base.py                # Imports all models for Alembic autogenerate
│   ├── models/
│   │   ├── users.py               # User (admin/teacher/student)
│   │   ├── offerings.py           # Offering (tutoring service)
│   │   ├── scheduling.py          # ScheduleEvent (individual session)
│   │   ├── change_requests.py     # EventChangeRequest (bilateral reschedule proposals)
│   │   ├── series.py              # RecurringSeries
│   │   ├── availability.py        # UnavailableBlock
│   │   └── unavail_series.py      # RecurringUnavailSeries
│   ├── schemas/                   # Pydantic request/response models
│   ├── services/
│   │   ├── series.py              # generate_events() — pure Python, no DB
│   │   ├── unavailability.py      # generate_unavailable_blocks()
│   │   ├── email.py               # Resend API wrapper + change-request email helpers
│   │   ├── chat.py                # OllamaChatService / BedrockChatService / DisabledChatService
│   │   └── reminders.py           # Upcoming-session reminder email logic
│   ├── static/
│   │   ├── css/
│   │   │   ├── input.css          # Tailwind source
│   │   │   └── style.css          # Compiled CSS (committed to repo)
│   │   ├── img/teachers/          # Uploaded teacher photos (runtime, gitignored)
│   │   └── js/                    # FullCalendar + series/unavail panel JS
│   └── templates/
│       ├── base.html
│       ├── landing/               # index, teachers, teacher_profile, subject_detail, contact
│       ├── auth/login.html
│       ├── admin/                 # dashboard, calendar, users
│       ├── teacher/               # dashboard, calendar, proposals
│       ├── student/               # dashboard, calendar, proposals
│       ├── components/            # HTMX fragments: navbars, panels, chat widget, CR form
│       └── errors/403.html
├── alembic/
│   ├── env.py                     # Async Alembic runner
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 987a86e04ae0_*.py      # UnavailableBlocks
│       ├── 2816b3ee1935_*.py      # RecurringSeries + series_id on events
│       ├── da0d2e951ef7_*.py      # RecurringUnavailSeries
│       ├── 1d4d6c1fa5a5_*.py      # Teacher profile fields (photo_url, bio, specialties)
│       ├── 698e615463d4_*.py      # reminder_sent_at on schedule_events
│       ├── 768151a670c1_*.py      # Composite indexes (teacher_id+start_time, student_id+start_time)
│       ├── d4260c02a08c_*.py      # EventChangeRequest table + 3 indexes
│       └── 18f3e895b0f9_*.py      # Drop old reschedule_proposals table (current head)
├── tests/
│   ├── conftest.py                # DB override, shared client fixture
│   ├── test_auth.py
│   ├── test_security.py
│   ├── test_authorization.py
│   ├── test_health.py
│   ├── test_admin_users.py
│   ├── test_routes_admin.py
│   ├── test_routes_teacher.py
│   ├── test_routes_student.py
│   ├── test_routes_profile.py
│   ├── test_landing_redesign.py
│   ├── test_api_events.py
│   ├── test_api_offerings.py
│   ├── test_api_availability.py
│   ├── test_api_stats.py
│   ├── test_double_booking.py
│   ├── test_series_generation.py
│   ├── test_series_schemas.py
│   ├── test_series_api.py
│   ├── test_unavail_series.py
│   ├── test_api_unavail_series.py
│   ├── test_teacher_profile_api.py
│   ├── test_cache.py
│   ├── test_calendar_performance.py
│   └── test_change_requests.py
├── scripts/
│   ├── seed_demo.py               # 5 teachers, 15 students, ~370 events
│   ├── add_overlap_demo.py        # Overlap events for UI testing
│   └── backup_db.py               # pg_dump → S3 backup
├── docker-compose.yml
├── docker-entrypoint.sh           # Migrations → optional seed → uvicorn
├── Dockerfile
├── requirements.txt
├── tailwind.config.js
├── package.json
└── pytest.ini
```

---

## 4. Database Schema

### Users (`users`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `role` | ENUM | `admin` / `teacher` / `student` |
| `email` | VARCHAR | Unique |
| `hashed_password` | VARCHAR | bcrypt hash |
| `full_name` | VARCHAR | |
| `photo_url` | VARCHAR(512) | Nullable; path to uploaded JPEG |
| `bio` | TEXT | Nullable; teacher public bio |
| `specialties` | VARCHAR(256) | Nullable; comma-separated subjects |
| `created_at` | TIMESTAMP WITH TIME ZONE | Server default |

### Offerings (`offerings`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `title` | VARCHAR | |
| `description` | TEXT | Nullable |
| `base_price_per_hour` | NUMERIC(10,2) | |
| `teacher_id` | UUID | FK → users |

### Schedule Events (`schedule_events`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `title` | VARCHAR | |
| `start_time` | TIMESTAMP WITH TIME ZONE | Composite index with teacher_id and student_id |
| `end_time` | TIMESTAMP WITH TIME ZONE | |
| `offering_id` | UUID | FK → offerings |
| `teacher_id` | UUID | FK → users |
| `student_id` | UUID | Nullable FK → users |
| `series_id` | UUID | Nullable FK → recurring_series (SET NULL on delete, indexed) |
| `status` | ENUM | `scheduled` / `completed` / `cancelled` |
| `reminder_sent_at` | TIMESTAMP WITH TIME ZONE | Nullable; set when reminder email sent |

### Event Change Requests (`event_change_requests`)

Replaces the old `reschedule_proposals` table. Bilateral — either teacher or student can propose.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `event_id` | UUID | FK → schedule_events (CASCADE DELETE); indexed |
| `proposer_id` | UUID | FK → users; indexed |
| `responder_id` | UUID | FK → users |
| `new_start` | TIMESTAMP WITH TIME ZONE | |
| `new_end` | TIMESTAMP WITH TIME ZONE | |
| `note` | VARCHAR(500) | Nullable |
| `status` | ENUM | `pending` / `accepted` / `rejected` / `cancelled` |
| `created_at` | TIMESTAMP WITH TIME ZONE | Server default |
| `resolved_at` | TIMESTAMP WITH TIME ZONE | Nullable; set on accept/reject/cancel |

### Recurring Series (`recurring_series`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `teacher_id` | UUID | FK → users |
| `student_id` | UUID | Nullable FK → users |
| `offering_id` | UUID | FK → offerings |
| `title` | VARCHAR | |
| `start_date` | DATE | First week anchor |
| `interval_weeks` | INT | ≥ 1 (CHECK constraint) |
| `day_slots` | JSONB | `[{day, hour, minute, duration_minutes}]` |
| `end_date` | DATE | Nullable; one of end_date/end_count required |
| `end_count` | INT | Nullable; max 200 (CHECK constraint) |
| `created_at` | TIMESTAMP WITH TIME ZONE | Server default |

### Unavailable Blocks (`unavailable_blocks`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → users (indexed) |
| `series_id` | UUID | Nullable FK → recurring_unavail_series (SET NULL, indexed) |
| `start_time` | TIMESTAMP WITH TIME ZONE | |
| `end_time` | TIMESTAMP WITH TIME ZONE | |
| `note` | TEXT | Nullable |

### Recurring Unavail Series (`recurring_unavail_series`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → users (indexed) |
| `note` | TEXT | Nullable |
| `start_date` | DATE | |
| `interval_weeks` | INT | ≥ 1 |
| `day_slots` | JSONB | Same structure as recurring_series |
| `end_date` | DATE | Nullable |
| `end_count` | INT | Nullable; max 200 |
| `created_at` | TIMESTAMP WITH TIME ZONE | Server default |

### Entity Relationships

```
User (admin)     ──creates──▶  Offering
User (teacher)   ──teaches──▶  ScheduleEvent ◀──enrolled── User (student)
User (teacher)   ──owns──────▶ RecurringSeries ──generates──▶ ScheduleEvent
User (teacher)   ──creates──▶  UnavailableBlock
User             ──owns──────▶ RecurringUnavailSeries ──generates──▶ UnavailableBlock
User             ──proposes──▶ EventChangeRequest ◀──responds── User
```

Current Alembic head: `18f3e895b0f9`

---

## 5. Authentication & Authorization

### Session Mechanism

Sessions use **itsdangerous** `URLSafeTimedSerializer` with:
- `SECRET_KEY` from environment
- 14-day expiry (`max_age=1209600`)
- Stored in a signed cookie named `session`

No JWT, no OAuth. Simple and stateless enough for an MVP.

### Login Flow

1. User submits `POST /login` with email + password
2. App loads User from DB, calls `verify_password()`
3. On success: serializes `{"user_id": str(user.id)}` → signed token → sets cookie
4. Redirects to role-appropriate dashboard (`/admin/`, `/teacher/`, `/student/`)

### Dependencies (FastAPI)

```python
get_current_user          # Returns User or None (does not raise)
require_auth              # Raises _LoginRedirect (303) if unauthenticated
require_admin             # require_role(UserRole.ADMIN)
require_teacher_or_admin  # require_role(UserRole.TEACHER, UserRole.ADMIN)
require_student           # require_role(UserRole.STUDENT)
```

### Roles

| Role | Access |
|------|--------|
| `admin` | Full access to all dashboards, user management, calendar oversight |
| `teacher` | Teacher dashboard, own calendar, bilateral proposals, profile edit |
| `student` | Student dashboard, own calendar, bilateral proposals |

---

## 6. Routes & Endpoints

### Public Landing (`routes_landing.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Homepage — hero, featured teachers, subjects; passes `chat_available` to template |
| GET | `/contact` | Contact form page |
| POST | `/contact/submit` | Submits form, returns HTMX success/error fragment |
| GET | `/nauczyciele` | All teachers list |
| GET | `/nauczyciele/{teacher_id}` | Individual teacher public profile |
| GET | `/przedmioty/matematyka` | Math & Physics subject detail |
| GET | `/przedmioty/informatyka` | IT & Programming subject detail |
| GET | `/przedmioty/jezyki-obce` | Languages subject detail |

### Auth (`routes_auth.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/login` | Login form (auto-redirects if already logged in) |
| POST | `/login` | Authenticate + set session cookie |
| POST | `/logout` | Clear cookie, redirect to login |

### Teacher Dashboard (`routes_teacher.py`) — requires teacher or admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/teacher/` | Upcoming sessions list + profile edit card |
| GET | `/teacher/calendar` | FullCalendar page |
| GET | `/teacher/proposals` | Bilateral proposals page (incoming + outgoing) |

### Student Dashboard (`routes_student.py`) — requires student

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/` | Upcoming + past sessions |
| GET | `/student/calendar` | FullCalendar page |
| GET | `/student/proposals` | Bilateral proposals page (incoming + outgoing) |

### Admin Dashboard (`routes_admin.py`) — requires admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/` | Dashboard with stats and offerings list |
| GET | `/admin/calendar` | FullCalendar page |
| GET | `/admin/users` | User management table |
| POST | `/admin/users/create` | Create user account |
| POST | `/admin/users/{id}/role` | Change user role (HTMX swap) |
| POST | `/admin/users/{id}/reset-password` | Reset password (HTMX swap) |
| POST | `/admin/offerings/create` | Create a new tutoring offering |

### Change Requests — bilateral proposals (`routes_change_requests.py`) — requires auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/change-requests` | Create proposal (proposer inferred from session, responder from event) |
| PATCH | `/api/change-requests/{id}/accept` | Accept; updates event times, invalidates cache |
| PATCH | `/api/change-requests/{id}/reject` | Reject proposal |
| PATCH | `/api/change-requests/{id}/cancel` | Cancel own pending proposal |
| GET | `/api/change-requests` | List proposals scoped to current user (role-filtered) |
| GET | `/api/change-requests/pending-count` | Plain-text count for HTMX navbar badge polling |

### JSON API (`routes_api.py`)

**Schedule Events**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/events` | T\|A | Date-range filtered; Redis-cached; `?teacher_id=` or `?student_id=` |
| POST | `/api/events` | T\|A | Create single event |
| PATCH | `/api/events/{id}` | T\|A | Update event (teacher: own only) |
| DELETE | `/api/events/{id}` | T\|A | Delete event (teacher: own only) |

**Offerings**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/offerings` | T\|A | All offerings |
| POST | `/api/offerings` | T\|A | Create offering |

**Availability**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/availability/{user_id}` | T\|A | Unavailable blocks for FullCalendar |
| POST | `/api/availability` | T\|A | Create single unavailable block |

**Recurring Series**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/series` | T\|A | Create series + generate all events |
| GET | `/api/series/{id}` | T\|A | Read series rule |
| DELETE | `/api/series/{id}/from/{event_id}` | T\|A | Delete from event onwards |
| PATCH | `/api/series/{id}/from/{event_id}` | T\|A | Edit series from ISO week |

**Recurring Unavailability**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/unavailability-series` | T\|A | Create recurring unavailability |
| GET | `/api/unavailability-series/{id}` | T\|A | Read series rule |
| DELETE | `/api/unavailability-series/{id}/from/{block_id}` | T\|A | Delete from block onwards |
| PATCH | `/api/unavailability-series/{id}/from/{block_id}` | T\|A | Edit from block onwards |

**Teacher Profile**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/teachers/me/photo` | Teacher | Upload photo; returns `<img>` HTML fragment |
| POST | `/api/admin/teachers/{id}/photo` | Admin | Admin uploads teacher photo |
| PATCH | `/api/teachers/me/profile` | Teacher | Update bio + specialties |
| PATCH | `/api/admin/teachers/{id}/profile` | Admin | Admin updates teacher profile |

**AI Chat**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/chat` | None | SSE stream — requires `LLM_PROVIDER` != `disabled` |

**Misc**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/teachers` | T\|A | All teachers (for dropdowns) |
| GET | `/api/students` | T\|A | All students |
| GET | `/api/stats` | Admin | Counts (scheduled/completed/cancelled, offerings) |
| GET | `/health` | None | Liveness probe — returns `{"status":"ok"}` |

---

## 7. Business Logic & Services

### Recurring Series Generation (`app/services/series.py`)

`generate_events(payload, series_id) → list[ScheduleEvent]`

Pure Python function — no database calls. Algorithm:
1. Anchor `start_date` to Monday of its ISO week.
2. Walk forward by `interval_weeks` per iteration.
3. For each week, expand `day_slots` → `(start_dt, end_dt)` pairs in UTC.
4. Stop when `end_count` events generated OR start of next week exceeds `end_date`.
5. Hard cap: maximum 200 events.
6. Return list sorted by `start_time`.

Conflict detection queries `UnavailableBlock` for the teacher and student and returns warnings (non-blocking — series is still created).

### Recurring Unavailability Generation (`app/services/unavailability.py`)

`generate_unavailable_blocks(payload, series_id) → list[UnavailableBlock]`

Mirrors `generate_events()`. Produces `UnavailableBlock` objects. Same 200-block hard cap.

### Email Service (`app/services/email.py`)

Wraps Resend API (`POST /emails`). Falls back to `logger.info()` when `RESEND_API_KEY` is empty.

Functions:
- `send_contact_email(form)` — contact form submission
- `send_change_request_email(event, cr, proposer, responder)` — new proposal notification
- `send_change_request_outcome_email(event, cr, proposer, responder)` — accept/reject notification

### Redis Cache (`app/core/cache.py`)

Async wrapper around `redis.asyncio`. When `REDIS_URL` is empty all operations are silent no-ops.

- Cache key format: `events:t|s:{uuid}:{YYYY-MM-DD}:{YYYY-MM-DD}`
- TTL: 300 s (5 min)
- Invalidated on: all event/series writes, change-request acceptance

### AI Chat Service (`app/services/chat.py`)

Selected by `settings.LLM_PROVIDER`:

| Provider | Class | Notes |
|----------|-------|-------|
| `disabled` | `DisabledChatService` | Returns unavailability notice immediately |
| `ollama` | `OllamaChatService` | Streams from local Ollama (`/api/chat`); model set by `OLLAMA_MODEL` |
| `bedrock` | `BedrockChatService` | `invoke_model_with_response_stream` via boto3; requires IAM role |

All three implement `async def stream(messages) -> AsyncIterator[str]`. The chat route in `routes_api.py` wraps the iterator in an SSE response (`text/event-stream`, `data: {"text":"…"}\n\n`).

### Photo Upload (`app/api/routes_api.py`)

`_save_teacher_photo(file, teacher, target_id)` helper:
1. Reads multipart upload bytes.
2. Validates ≤ 2 MB.
3. Opens with Pillow (`Image.open`) — rejects non-image bytes.
4. Converts to RGB JPEG, saves to `app/static/img/teachers/{teacher_id}.jpg`.
5. Sets `teacher.photo_url = /static/img/teachers/{teacher_id}.jpg?v={uuid4}`.
6. Returns an HTML `<img>` fragment (for HTMX `outerHTML` swap).

---

## 8. Frontend Architecture

### Template Hierarchy

```
base.html
  └── Injects: navbar (per role), content block, footer
      ├── landing/*.html      (no auth required)
      ├── auth/login.html
      ├── admin/*.html        (require_admin)
      ├── teacher/*.html      (require_teacher_or_admin)
      ├── student/*.html      (require_student)
      └── components/*.html   (HTMX response fragments)
```

### HTMX Patterns

- **Form submissions** use `hx-post` / `hx-patch` with `hx-swap="outerHTML"` or `hx-swap="none"`.
- **Inline success toasts**: `hx-on::after-request` removes `.hidden` from a success span, then re-adds it after 2 s via `setTimeout`.
- **Photo upload**: `onchange="this.form.requestSubmit()"` triggers upload immediately on file select. Response is an `<img>` fragment that replaces the current photo element.
- **Role change / password reset**: Forms return updated `<form>` fragments to replace themselves.
- **Navbar badges**: `hx-get="/api/change-requests/pending-count"` with `hx-trigger="load, every 60s"` on all teacher/student/admin navbars.
- **Change request actions** (accept/reject/cancel): PATCH via HTMX `hx-swap="outerHTML"` on the card; returns an updated card or empty string on deletion.
- **Change request form**: uses `hx-ext="json-enc"` to send JSON rather than form-encoded body.

### FullCalendar Integration

Three JS files handle calendar configuration:

- `admin_calendar.js` — all teachers; create events and series; colour-coded by teacher (stable UUID hash); drag/resize/delete; context menu
- `teacher_calendar.js` — own events; create and edit own; unavailability
- `student_calendar.js` — read-only enrolled sessions

Calendar data from `/api/events?teacher_id=` or `?student_id=` (date-range lazy loading, Redis-cached).
Availability blocks from `/api/availability/{user_id}` as background events.

### Tailwind Custom Theme

```js
colors: {
  cream: "#f7f4ef",   // Light background
  ink:   "#1a1814",   // Dark text
  navy:  "#1a2744",   // Primary accent
  gold:  "#b8922a",   // Secondary accent
}
fonts: {
  sans:   "DM Sans",
  serif:  "Playfair Display",
  inter:  "Inter",
}
```

`style.css` is compiled and **committed to the repository** (no Node.js in Docker image).
Rebuild when templates change: `npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css`

---

## 9. Running Locally

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for Tailwind CSS build only)

### First run

```bash
cp .env.example .env
# Edit .env — defaults work for Docker Compose. Set a real SECRET_KEY.

docker compose up --build
```

Migrations run automatically via `docker-entrypoint.sh`. App at **http://localhost:8000**.

### Load demo data

```bash
docker compose exec web bash -c "cd /app && PYTHONPATH=/app python scripts/seed_demo.py"
```

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@ekorepetycje.pl | admin123 |
| Teacher | anna@eko.pl | haslo123 |
| Student | marek@student.pl | haslo123 |

### Optional: enable AI chat

```bash
# In .env:
LLM_PROVIDER=ollama

# Start with the AI profile (downloads ~2 GB model on first run):
docker compose --profile ai up --build
```

### Tailwind watch

```bash
npm install
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css --watch
```

### Useful commands

```bash
# Generate a migration
docker compose exec web alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec web alembic upgrade head

# Rollback one step
docker compose exec web alembic downgrade -1

# Run tests
docker compose exec web pytest tests/ -v

# Tail app logs
docker compose logs -f web
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | asyncpg connection string | required |
| `SECRET_KEY` | Session signing key | required |
| `DEBUG` | Enables uvicorn reload + verbose errors | `False` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Used by db service | `postgres` / `password` / `ekorepetycje` |
| `REDIS_URL` | Redis connection; empty = caching disabled | `""` |
| `RESEND_API_KEY` | Resend email API key; empty = log only | `""` |
| `RESEND_FROM_EMAIL` | Sender address | `onboarding@resend.dev` |
| `RESEND_TO_EMAIL` | Contact form recipient | `kontakt@ekorepetycje.pl` |
| `LLM_PROVIDER` | `disabled` / `ollama` / `bedrock` | `disabled` |
| `OLLAMA_URL` | Ollama base URL | `http://ollama:11434` |
| `OLLAMA_MODEL` | Model tag | `llama3.2:3b` |
| `BEDROCK_MODEL_ID` | Bedrock model ARN | `anthropic.claude-3-haiku-20240307-v1:0` |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile keys | test keys (always pass) |

---

## 10. Testing

### Run tests

```bash
docker compose exec web pytest tests/ -v
```

### Configuration (`pytest.ini`)

```ini
[pytest]
asyncio_mode = auto
```

All async tests are plain `async def` — no `@pytest.mark.asyncio` decorators needed.

### Fixtures (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `override_get_db` | autouse | Replaces `get_db()` with NullPool session; auto-applies to every test |
| `client` | function | `AsyncClient` with `ASGITransport` — in-process HTTP requests |
| `teacher_in_db` | function | Inserts a real TEACHER row, yields UUID, cleans up on teardown |

### Test Coverage

| File | What it tests |
|------|--------------|
| `test_auth.py` | Session sign/read, login form, wrong credentials |
| `test_security.py` | bcrypt hash/verify |
| `test_authorization.py` | Role-based access enforcement across all protected routes |
| `test_health.py` | `/health` liveness probe |
| `test_admin_users.py` | User creation endpoint |
| `test_routes_admin.py` | Admin dashboard pages and HTMX actions |
| `test_routes_teacher.py` | Teacher dashboard pages |
| `test_routes_student.py` | Student dashboard pages |
| `test_routes_profile.py` | Profile page |
| `test_landing_redesign.py` | All public pages, teacher section, subject pages, contact form |
| `test_api_events.py` | Event CRUD JSON API |
| `test_api_offerings.py` | Offerings API |
| `test_api_availability.py` | Unavailable blocks API |
| `test_api_stats.py` | Stats endpoint |
| `test_double_booking.py` | Concurrent booking conflict detection |
| `test_series_generation.py` | Recurrence algorithm (weekly/biweekly, end_count, end_date, caps) |
| `test_series_schemas.py` | Pydantic validation (DaySlot, SeriesCreate mutual exclusion) |
| `test_series_api.py` | Series CRUD API |
| `test_unavail_series.py` | Unavailability series generation |
| `test_api_unavail_series.py` | Unavailability series API |
| `test_teacher_profile_api.py` | Photo upload + PATCH profile (unauthenticated blocks) |
| `test_cache.py` | Redis cache set/get/invalidate (with Redis mock) |
| `test_calendar_performance.py` | Date-range filtering, Redis caching layer, cache invalidation |
| `test_change_requests.py` | Full bilateral proposal lifecycle (create, accept, reject, cancel, pending-count) |

---

## 11. AWS Deployment Guide

This section explains how to run the application in production on AWS using managed services.

### Architecture Overview

```
Internet
   │
   ▼
Route 53 (DNS)
   │
   ▼
CloudFront (CDN + HTTPS termination)
   │  ├── /static/* → S3 bucket (CSS, JS, teacher photos)
   │  └── everything else ↓
   ▼
Application Load Balancer (ALB)
   │
   ▼
ECS Fargate (FastAPI container, 1–N tasks)
   │
   ├──▶ RDS PostgreSQL 15 (private subnet)
   ├──▶ ElastiCache Redis (private subnet, optional)
   ├──▶ Amazon Bedrock (if LLM_PROVIDER=bedrock — IAM role, no extra keys)
   └──▶ Secrets Manager (DATABASE_URL, SECRET_KEY, RESEND_API_KEY, …)
```

### Step 1 — Prerequisites

```bash
pip install awscli
aws configure
```

### Step 2 — Create a VPC

1. **VPC → Your VPCs → Create VPC** → select **VPC and more**
2. Name: `ekorepetycje-vpc`, CIDR `10.0.0.0/16`, 2 AZs, 2 public + 2 private subnets, 1 NAT Gateway

### Step 3 — Create RDS PostgreSQL 15

- Engine: PostgreSQL 15, instance `db.t3.micro`, private subnet, no public access
- Security group: allow inbound 5432 from ECS security group only
- Note the endpoint — your `DATABASE_URL` will be:
  ```
  postgresql+asyncpg://postgres:<PASSWORD>@<endpoint>:5432/ekorepetycje
  ```

### Step 4 — (Optional) Create ElastiCache Redis

- Engine: Redis 7, `cache.t3.micro`, same private subnets as ECS
- Set `REDIS_URL=redis://<endpoint>:6379/0` in the task definition

### Step 5 — Store Secrets

```bash
aws secretsmanager create-secret --name ekorepetycje/DATABASE_URL \
  --secret-string "postgresql+asyncpg://postgres:<PASSWORD>@<endpoint>:5432/ekorepetycje"

aws secretsmanager create-secret --name ekorepetycje/SECRET_KEY \
  --secret-string "$(python -c 'import secrets; print(secrets.token_hex(32))')"

aws secretsmanager create-secret --name ekorepetycje/RESEND_API_KEY \
  --secret-string "re_..."
```

### Step 6 — Create ECR Repository

```bash
aws ecr create-repository --repository-name ekorepetycje --region eu-central-1
```

### Step 7 — ECS Task Definition

Container environment variables (from Secrets Manager):

```
DATABASE_URL         → secretsmanager:ekorepetycje/DATABASE_URL
SECRET_KEY           → secretsmanager:ekorepetycje/SECRET_KEY
RESEND_API_KEY       → secretsmanager:ekorepetycje/RESEND_API_KEY
REDIS_URL            → redis://<elasticache-endpoint>:6379/0
LLM_PROVIDER         → bedrock  (or disabled)
BEDROCK_MODEL_ID     → anthropic.claude-3-haiku-20240307-v1:0
AWS_DEFAULT_REGION   → us-east-1
TURNSTILE_SECRET_KEY → secretsmanager:ekorepetycje/TURNSTILE_SECRET_KEY
```

For Bedrock: attach `bedrock:InvokeModelWithResponseStream` IAM policy to the ECS task execution role — no API keys required.

### Step 8 — GitHub Actions CI/CD

Add these secrets to **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM user key (ECR + ECS permissions) |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret |
| `ECS_PRIVATE_SUBNET_IDS` | `subnet-xxx,subnet-yyy` |
| `ECS_SECURITY_GROUP_ID` | SG allowing DB + Redis access |

Push to `main` triggers the pipeline:
1. `pytest` + Alembic migrate on test DB
2. Tailwind build → Docker build → push to ECR
3. `alembic upgrade head` as one-off ECS task against prod DB
4. Update ECS service task definition → rolling deploy

### Rollback

```bash
aws ecs list-task-definitions --family-prefix ekorepetycje
aws ecs update-service \
  --cluster ekorepetycje-cluster \
  --service ekorepetycje-web \
  --task-definition ekorepetycje:<PREVIOUS_REVISION>
```
