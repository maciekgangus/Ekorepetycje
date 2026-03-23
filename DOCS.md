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

- **Public landing page** — marketing content, featured teachers, subject pages, contact form
- **Teacher management** — profiles with photos, bio, specialties
- **Admin dashboard** — user CRUD, role management, offering creation, proposal approval
- **Teacher dashboard** — upcoming sessions, calendar, reschedule proposals
- **Student dashboard** — session calendar, upcoming/past sessions
- **Scheduling system** — one-off events and recurring series with conflict detection
- **Availability management** — single and recurring unavailability blocks

The application is a server-rendered web app using HTMX for dynamic interactions. There is no client-side JavaScript framework — all interactivity is done via HTML fragments returned from the server.

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI (Python 3.11) |
| ORM | SQLAlchemy (async) |
| Database | PostgreSQL 15 |
| Migrations | Alembic (async runner) |
| ASGI server | Uvicorn |
| Templates | Jinja2 |
| Interactivity | HTMX 1.9 |
| Styling | Tailwind CSS v3 |
| Calendar UI | FullCalendar (loaded via CDN) |
| Auth | itsdangerous (signed cookies, 14-day session) |
| Password hashing | passlib + bcrypt |
| Image processing | Pillow |
| Validation | Pydantic v2 + pydantic-settings |
| Async DB driver | asyncpg |
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
│   │   ├── routes_api.py          # JSON API (FullCalendar, series, teacher photos)
│   │   └── dependencies.py        # get_db() session provider
│   ├── core/
│   │   ├── config.py              # Settings (DATABASE_URL, SECRET_KEY, DEBUG)
│   │   ├── security.py            # hash_password, verify_password
│   │   ├── auth.py                # Session signing, require_* dependencies
│   │   └── templates.py           # Jinja2Templates instance
│   ├── db/
│   │   ├── database.py            # AsyncEngine, AsyncSessionLocal, Base
│   │   └── base.py                # Imports all models for Alembic autogenerate
│   ├── models/
│   │   ├── users.py               # User (admin/teacher/student)
│   │   ├── offerings.py           # Offering (tutoring service)
│   │   ├── scheduling.py          # ScheduleEvent (individual session)
│   │   ├── proposals.py           # RescheduleProposal
│   │   ├── series.py              # RecurringSeries
│   │   ├── availability.py        # UnavailableBlock
│   │   └── unavail_series.py      # RecurringUnavailSeries
│   ├── schemas/                   # Pydantic request/response models
│   ├── services/
│   │   ├── series.py              # generate_events() — pure Python, no DB
│   │   ├── unavailability.py      # generate_unavailable_blocks()
│   │   └── email.py               # Email stubs (logs only, not yet wired)
│   ├── static/
│   │   ├── css/
│   │   │   ├── input.css          # Tailwind source
│   │   │   └── style.css          # Compiled CSS (committed)
│   │   ├── img/teachers/          # Uploaded teacher photos (runtime)
│   │   └── js/                    # FullCalendar + series/unavail panel JS
│   └── templates/
│       ├── base.html
│       ├── landing/               # index, teachers, teacher_profile, subject_detail, contact
│       ├── auth/login.html
│       ├── admin/                 # dashboard, calendar, users, proposals
│       ├── teacher/               # dashboard, calendar, proposals
│       ├── student/               # dashboard, calendar
│       ├── components/            # HTMX fragments: navbars, cards, panels, alerts
│       └── errors/403.html
├── alembic/
│   ├── env.py                     # Async Alembic runner
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 987a86e04ae0_*.py      # UnavailableBlocks + RescheduleProposals
│       ├── 2816b3ee1935_*.py      # RecurringSeries + series_id on events
│       ├── da0d2e951ef7_*.py      # RecurringUnavailSeries, generalise blocks
│       └── 1d4d6c1fa5a5_*.py      # Teacher profile fields (photo_url, bio, specialties)
├── tests/
│   ├── conftest.py                # DB override, shared client fixture, teacher_in_db
│   ├── test_auth.py
│   ├── test_security.py
│   ├── test_admin_users.py
│   ├── test_landing_redesign.py
│   ├── test_series_generation.py
│   ├── test_series_schemas.py
│   ├── test_series_api.py
│   └── test_teacher_profile_api.py
├── scripts/seed.py                # Seed script for local development
├── Dockerfile
├── docker-compose.yml
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
| `start_time` | TIMESTAMP WITH TIME ZONE | |
| `end_time` | TIMESTAMP WITH TIME ZONE | |
| `offering_id` | UUID | FK → offerings |
| `teacher_id` | UUID | FK → users |
| `student_id` | UUID | Nullable FK → users |
| `series_id` | UUID | Nullable FK → recurring_series (SET NULL on delete, indexed) |
| `status` | ENUM | `scheduled` / `completed` / `cancelled` |

### Reschedule Proposals (`reschedule_proposals`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `event_id` | UUID | FK → schedule_events |
| `proposed_by` | UUID | FK → users |
| `new_start` | TIMESTAMP WITH TIME ZONE | |
| `new_end` | TIMESTAMP WITH TIME ZONE | |
| `status` | ENUM | `pending` / `approved` / `rejected` |
| `created_at` | TIMESTAMP WITH TIME ZONE | Server default |

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
User (teacher)   ──creates──▶  RescheduleProposal
User             ──owns──────▶ RecurringUnavailSeries ──generates──▶ UnavailableBlock
```

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
get_current_user   # Returns User or None (does not raise)
require_auth       # Raises _LoginRedirect (303) if unauthenticated
require_admin      # require_role(UserRole.ADMIN)
require_teacher_or_admin  # require_role(UserRole.TEACHER, UserRole.ADMIN)
```

All protected routes inject one of these as a FastAPI dependency.

### Roles

| Role | Access |
|------|--------|
| `admin` | Full access to all dashboards, user management, proposal approval |
| `teacher` | Teacher dashboard, own calendar, propose reschedules, edit own profile |
| `student` | Student dashboard, own calendar |

---

## 6. Routes & Endpoints

### Public Landing (`routes_landing.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Homepage — hero, featured teachers (photo+bio not null, limit 3), subjects section |
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
| GET | `/teacher/proposals` | Reschedule proposals sent by this teacher |
| POST | `/teacher/proposals/create` | Submit reschedule proposal (HTMX) |

### Student Dashboard (`routes_student.py`) — requires student

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/` | Upcoming + past sessions |
| GET | `/student/calendar` | FullCalendar page |

### Admin Dashboard (`routes_admin.py`) — requires admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/` | Dashboard with stats and offerings list |
| GET | `/admin/calendar` | FullCalendar page |
| GET | `/admin/users` | User management table |
| POST | `/admin/users/create` | Create user account |
| POST | `/admin/users/{id}/role` | Change user role (HTMX swap) |
| POST | `/admin/users/{id}/reset-password` | Reset password (HTMX swap) |
| GET | `/admin/proposals` | All pending reschedule proposals |
| POST | `/admin/proposals/{id}/approve` | Approve proposal, update event times |
| POST | `/admin/proposals/{id}/reject` | Reject proposal |
| POST | `/admin/offerings/create` | Create a new tutoring offering |

### JSON API (`routes_api.py`)

**Schedule Events**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/events` | T\|A | All events; filter by `?teacher_id=` or `?student_id=` |
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

**Misc**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/teachers` | T\|A | All teachers (for dropdowns) |
| GET | `/api/students` | T\|A | All students |
| GET | `/api/stats` | Admin | Counts (scheduled/completed/cancelled, offerings, pending proposals) |
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

Conflict detection in the route layer queries `UnavailableBlock` for the teacher and student
and returns warnings (non-blocking — series is still created).

### Recurring Unavailability Generation (`app/services/unavailability.py`)

`generate_unavailable_blocks(payload, series_id) → list[UnavailableBlock]`

Mirrors `generate_events()`. Produces `UnavailableBlock` objects. Same 200-block hard cap.

### Email Service (`app/services/email.py`)

Currently **stubs** — logs to the application logger but does not send real email.
To wire up a real provider (e.g. SendGrid, Resend, AWS SES), replace the function bodies.

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
- **Inline success toasts**: `hx-on::after-request` removes `.hidden` from a success span, then re-adds it after 2 seconds via `setTimeout`.
- **Photo upload**: `onchange="this.form.requestSubmit()"` triggers upload immediately on file select. Response is an `<img>` HTML fragment that replaces the current photo element.
- **Role change / password reset**: Forms return updated `<form>` fragments to replace themselves.

### FullCalendar Integration

Each dashboard has a calendar page. FullCalendar is loaded from CDN. Three JS files handle configuration:

- `admin_calendar.js` — can view/edit all teachers, create events and series
- `teacher_calendar.js` — views own events, can create and edit own
- `student_calendar.js` — read-only view of own enrolled sessions

Calendar data is fetched from `/api/events?teacher_id=` or `?student_id=` as JSON.
Availability blocks are fetched from `/api/availability/{user_id}` as background events.

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

Build command: `npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css`

---

## 9. Running Locally

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ (for Tailwind CSS build only)

### First run

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env with your values (defaults work for Docker Compose)

# 2. Start all services
docker-compose up --build

# 3. Apply database migrations
docker-compose exec web alembic upgrade head

# 4. (Optional) Seed the database with test data
docker-compose exec web python scripts/seed.py
```

The app will be available at **http://localhost:8000**.

### Tailwind watch (development)

```bash
npm install
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css --watch
```

### Useful commands

```bash
# Generate a new migration after model changes
docker-compose exec web alembic revision --autogenerate -m "description"

# Apply migrations
docker-compose exec web alembic upgrade head

# Rollback one step
docker-compose exec web alembic downgrade -1

# Run tests
docker-compose exec web pytest tests/ -v

# Tail app logs
docker-compose logs -f web
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | asyncpg connection string | `postgresql+asyncpg://postgres:pass@db:5432/ekorepetycje` |
| `SECRET_KEY` | Session signing key (keep secret) | `some-random-64-char-string` |
| `DEBUG` | Enables reload + verbose errors | `True` / `False` |
| `POSTGRES_USER` | DB username (used by docker-compose db service) | `postgres` |
| `POSTGRES_PASSWORD` | DB password | `password` |
| `POSTGRES_DB` | DB name | `ekorepetycje` |

---

## 10. Testing

### Run tests

```bash
docker-compose exec web pytest tests/ -v
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
| `test_admin_users.py` | User creation endpoint |
| `test_landing_redesign.py` | All public pages, teacher section, subject pages, contact form |
| `test_series_generation.py` | Recurrence algorithm (weekly/biweekly, end_count, end_date, caps) |
| `test_series_schemas.py` | Pydantic validation (DaySlot, SeriesCreate mutual exclusion) |
| `test_series_api.py` | API series CRUD |
| `test_teacher_profile_api.py` | Photo upload + PATCH profile (unauthenticated blocks) |

---

## 11. AWS Deployment Guide

This section explains how to take the Docker-based application and run it in production on AWS.
The recommended architecture uses managed services to minimise operational overhead.

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
   ├──▶ RDS PostgreSQL (private subnet)
   ├──▶ S3 (teacher photo uploads, write path)
   └──▶ Secrets Manager (DATABASE_URL, SECRET_KEY)
```

### Step 1 — Prerequisites

Install and configure the AWS CLI:

```bash
# Install
pip install awscli

# Configure credentials
aws configure
# Enter: Access Key ID, Secret Access Key, region (e.g. eu-central-1), output format (json)
```

Install the AWS CDK or use the Console. This guide uses the Console + CLI for clarity.

---

### Step 2 — Create a VPC

1. Open **VPC → Your VPCs → Create VPC**.
2. Select **VPC and more** (wizard).
3. Configure:
   - Name: `ekorepetycje-vpc`
   - IPv4 CIDR: `10.0.0.0/16`
   - Availability Zones: 2
   - Public subnets: 2 (for ALB)
   - Private subnets: 2 (for ECS tasks and RDS)
   - NAT Gateways: 1 (so private tasks can pull container images)
4. Click **Create VPC**.

Note the VPC ID, subnet IDs, and security group IDs — you will need them later.

---

### Step 3 — Create an RDS PostgreSQL Database

1. Open **RDS → Create database**.
2. Settings:
   - Engine: **PostgreSQL 15**
   - Template: **Production** (or Free Tier for testing)
   - DB instance identifier: `ekorepetycje-db`
   - Master username: `postgres`
   - Master password: generate a strong one, save it
   - DB instance class: `db.t3.micro` (small MVP), `db.t3.small` for modest traffic
   - Storage: 20 GB gp2, enable autoscaling
   - VPC: your VPC above
   - Subnet group: create one using your 2 private subnets
   - Public access: **No**
   - Security group: create `rds-sg` that allows inbound 5432 from the ECS security group only
   - Initial database name: `ekorepetycje`
3. Click **Create database**.

After creation, note the **Endpoint** (looks like `ekorepetycje-db.xxxxxx.eu-central-1.rds.amazonaws.com`).

Your `DATABASE_URL` will be:
```
postgresql+asyncpg://postgres:<PASSWORD>@ekorepetycje-db.xxxxxx.eu-central-1.rds.amazonaws.com:5432/ekorepetycje
```

---

### Step 4 — Store Secrets in AWS Secrets Manager

Never put credentials in environment variables as plaintext in ECS task definitions.

```bash
# Store DATABASE_URL
aws secretsmanager create-secret \
  --name ekorepetycje/DATABASE_URL \
  --secret-string "postgresql+asyncpg://postgres:<PASSWORD>@<RDS_ENDPOINT>:5432/ekorepetycje"

# Store SECRET_KEY (generate a 64-character random string)
aws secretsmanager create-secret \
  --name ekorepetycje/SECRET_KEY \
  --secret-string "$(openssl rand -hex 32)"
```

Note the ARNs of both secrets.

---

### Step 5 — Create an S3 Bucket for Static Files & Teacher Photos

```bash
# Create bucket (replace REGION and ACCOUNT_ID)
aws s3api create-bucket \
  --bucket ekorepetycje-static \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

# Enable static website hosting (for serving CSS/JS/images)
aws s3 website s3://ekorepetycje-static/ \
  --index-document index.html

# Block public access except for CloudFront (set bucket policy later)
```

**Upload compiled static assets:**

```bash
aws s3 sync app/static/ s3://ekorepetycje-static/static/ \
  --cache-control "max-age=31536000,public" \
  --exclude "*.py"
```

> **Note**: Because the app currently serves static files from the local filesystem
> (`/static/`), you will need to either:
> - Continue serving them via the app container (simplest, works as-is), or
> - Switch to boto3 for S3 uploads and update `photo_url` to S3/CloudFront URLs.
>
> For an MVP, serving from the container is fine. For production scale, use S3.

---

### Step 6 — Build and Push the Docker Image to ECR

**Create an ECR repository:**

```bash
aws ecr create-repository \
  --repository-name ekorepetycje \
  --region eu-central-1
```

Note the repository URI: `<ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com/ekorepetycje`

**Build and push:**

```bash
# Authenticate Docker with ECR
aws ecr get-login-password --region eu-central-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com

# Build production image (no --reload)
docker build -t ekorepetycje .

# Tag
docker tag ekorepetycje:latest \
  <ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com/ekorepetycje:latest

# Push
docker push <ACCOUNT_ID>.dkr.ecr.eu-central-1.amazonaws.com/ekorepetycje:latest
```

---

### Step 7 — Create an ECS Cluster and Task Definition

**Create the cluster:**

```bash
aws ecs create-cluster --cluster-name ekorepetycje-cluster
```

**Create an IAM role for ECS tasks** (to read Secrets Manager):

1. Go to **IAM → Roles → Create role**.
2. Trusted entity: **AWS service → Elastic Container Service Task**.
3. Attach policies:
   - `AmazonECSTaskExecutionRolePolicy` (pull images, write logs)
   - Custom inline policy for Secrets Manager:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Action": ["secretsmanager:GetSecretValue"],
         "Resource": [
           "arn:aws:secretsmanager:eu-central-1:<ACCOUNT>:secret:ekorepetycje/*"
         ]
       }]
     }
     ```
4. Name the role: `ekorepetycje-task-execution-role`

**Create the Task Definition** (save as `task-definition.json`):

```json
{
  "family": "ekorepetycje",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT>:role/ekorepetycje-task-execution-role",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT>:role/ekorepetycje-task-execution-role",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "<ACCOUNT>.dkr.ecr.eu-central-1.amazonaws.com/ekorepetycje:latest",
      "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:eu-central-1:<ACCOUNT>:secret:ekorepetycje/DATABASE_URL"
        },
        {
          "name": "SECRET_KEY",
          "valueFrom": "arn:aws:secretsmanager:eu-central-1:<ACCOUNT>:secret:ekorepetycje/SECRET_KEY"
        }
      ],
      "environment": [
        {"name": "DEBUG", "value": "False"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ekorepetycje",
          "awslogs-region": "eu-central-1",
          "awslogs-stream-prefix": "web"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

Register it:

```bash
# Create the CloudWatch log group first
aws logs create-log-group --log-group-name /ecs/ekorepetycje

# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

---

### Step 8 — Create an Application Load Balancer

1. Open **EC2 → Load Balancers → Create Load Balancer → Application Load Balancer**.
2. Settings:
   - Name: `ekorepetycje-alb`
   - Scheme: **Internet-facing**
   - VPC: your VPC
   - Subnets: your 2 **public** subnets
   - Security group: create `alb-sg` allowing inbound 80 and 443 from `0.0.0.0/0`
3. **Listeners**:
   - Port 80 → HTTP → redirect to HTTPS (add after certificate)
   - Port 443 → HTTPS → forward to target group
4. **Target group**:
   - Type: **IP** (required for Fargate awsvpc)
   - Protocol: HTTP, Port: 8000
   - Health check path: `/health`
   - Name: `ekorepetycje-tg`
5. Complete creation. Note the ALB DNS name.

---

### Step 9 — TLS Certificate via ACM

1. Open **Certificate Manager → Request certificate**.
2. Request a **public** certificate.
3. Domain: `ekorepetycje.pl` and `www.ekorepetycje.pl` (or your domain).
4. Validation method: **DNS validation**.
5. Add the CNAME records it provides to your DNS (Route 53 or external registrar).
6. Wait for status to become **Issued** (usually 5–30 minutes).
7. Attach the certificate to the ALB HTTPS listener.

---

### Step 10 — Create the ECS Service

```bash
aws ecs create-service \
  --cluster ekorepetycje-cluster \
  --service-name ekorepetycje-web \
  --task-definition ekorepetycje \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[<PRIVATE_SUBNET_1>,<PRIVATE_SUBNET_2>],
    securityGroups=[<ECS_SG_ID>],
    assignPublicIp=DISABLED
  }" \
  --load-balancers "targetGroupArn=<TARGET_GROUP_ARN>,containerName=web,containerPort=8000" \
  --health-check-grace-period-seconds 120
```

Create the ECS security group (`ecs-sg`) allowing inbound 8000 from `alb-sg` only, and all outbound traffic.

---

### Step 11 — Run Migrations

After the service is running, you need to apply Alembic migrations to RDS.
The easiest way is to run a one-off task:

```bash
aws ecs run-task \
  --cluster ekorepetycje-cluster \
  --task-definition ekorepetycje \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[<PRIVATE_SUBNET_1>],
    securityGroups=[<ECS_SG_ID>],
    assignPublicIp=DISABLED
  }" \
  --overrides '{
    "containerOverrides": [{
      "name": "web",
      "command": ["alembic", "upgrade", "head"]
    }]
  }'
```

Check the task logs in CloudWatch (`/ecs/ekorepetycje`) to confirm migrations succeeded.

---

### Step 12 — Configure Route 53 & CloudFront (Optional but Recommended)

**Route 53:**

1. Create a Hosted Zone for your domain.
2. Add an **A record** (alias) pointing to the ALB DNS name.
3. Add a **CNAME** for `www` pointing to the bare domain.

**CloudFront (for performance + global CDN):**

1. Create a distribution.
2. Origin: your ALB DNS name (HTTP only; CloudFront handles HTTPS).
3. Behaviours:
   - `/static/*` → can also point to S3 if you move static assets there.
   - `Default (*)` → forward to ALB.
4. Viewer protocol policy: **Redirect HTTP to HTTPS**.
5. Alternate domain: `ekorepetycje.pl`, attach ACM certificate.
6. Update Route 53 A record to point to the CloudFront distribution instead of the ALB.

---

### Step 13 — Auto-Scaling (Optional)

```bash
# Register the ECS service as a scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/ekorepetycje-cluster/ekorepetycje-web \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 4

# Scale out when CPU > 70%
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/ekorepetycje-cluster/ekorepetycje-web \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }'
```

---

### Step 14 — CI/CD with GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: eu-central-1

      - name: Build Tailwind CSS
        run: |
          npm install
          npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/ekorepetycje:$IMAGE_TAG .
          docker push $ECR_REGISTRY/ekorepetycje:$IMAGE_TAG
          docker tag $ECR_REGISTRY/ekorepetycje:$IMAGE_TAG $ECR_REGISTRY/ekorepetycje:latest
          docker push $ECR_REGISTRY/ekorepetycje:latest

      - name: Run Alembic migrations
        run: |
          aws ecs run-task \
            --cluster ekorepetycje-cluster \
            --task-definition ekorepetycje \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=[${{ secrets.PRIVATE_SUBNET_1 }}],securityGroups=[${{ secrets.ECS_SG_ID }}],assignPublicIp=DISABLED}" \
            --overrides '{"containerOverrides":[{"name":"web","command":["alembic","upgrade","head"]}]}'

      - name: Deploy new task definition to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: task-definition.json
          service: ekorepetycje-web
          cluster: ekorepetycje-cluster
          wait-for-service-stability: true
```

Add these secrets to GitHub: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `PRIVATE_SUBNET_1`, `ECS_SG_ID`.

---

### Cost Estimate (eu-central-1, 2025)

| Service | Config | Monthly cost |
|---------|--------|-------------|
| ECS Fargate | 1 task × 0.5 vCPU / 1 GB, ~720h | ~$15 |
| RDS PostgreSQL | db.t3.micro, 20 GB, single-AZ | ~$15 |
| ALB | 1 ALB + ~1M requests | ~$18 |
| NAT Gateway | 1 gateway + ~10 GB data | ~$35 |
| ECR | ~500 MB storage | ~$0.05 |
| CloudFront | 1M requests, 10 GB transfer | ~$2 |
| Route 53 | 1 hosted zone | ~$0.50 |
| Secrets Manager | 2 secrets | ~$0.80 |
| CloudWatch Logs | ~1 GB/month | ~$0.50 |
| **Total estimate** | | **~$87/month** |

> The NAT Gateway is the biggest line item. You can eliminate it by giving Fargate tasks
> a public IP (set `assignPublicIp=ENABLED`, move to public subnets) — this reduces cost
> significantly for a small MVP but is slightly less secure.

---

### Production Checklist

Before going live, verify:

- [ ] `DEBUG=False` in production
- [ ] `SECRET_KEY` is a strong random value stored in Secrets Manager
- [ ] RDS is in private subnets, not publicly accessible
- [ ] ECS security group allows inbound 8000 from ALB only
- [ ] ALB listener on 80 redirects to 443
- [ ] ACM certificate is attached to ALB / CloudFront
- [ ] Alembic migrations have been applied (`alembic upgrade head`)
- [ ] Teacher photo upload directory exists inside the container or photos are stored in S3
- [ ] CloudWatch log group created and container logs are flowing
- [ ] Health check at `/health` returns 200
- [ ] Test login, teacher profile edit, admin user creation end-to-end

---

### Current Limitations (MVP to Production Gaps)

| Feature | Current State | Production Fix |
|---------|--------------|----------------|
| Email | Stubs (logs only) | Wire up AWS SES or Resend in `app/services/email.py` |
| Teacher photos | Stored on container filesystem | Move to S3; update `_save_teacher_photo()` to use `boto3.upload_fileobj()` |
| Payment | Not implemented | Integrate Stripe or PayU |
| Password reset | Admin resets only | Add self-service reset flow with email token |
| Student enrollment | Events created manually by admin/teacher | Add student booking flow |
| Multi-region | Single region | Low priority until traffic grows |
