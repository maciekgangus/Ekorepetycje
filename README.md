# Ekorepetycje

A modern tutoring platform MVP — FastAPI backend, Jinja2/HTMX frontend, FullCalendar scheduling, PostgreSQL + Redis, AI chat widget. Built with a Vercel/Next.js dark aesthetic.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Architecture & File Structure](#architecture--file-structure)
3. [Database Schema](#database-schema)
4. [Feature Overview](#feature-overview)
5. [Local Development](#local-development)
6. [Environment Variables](#environment-variables)
7. [Homelab Deployment + Cloudflare Tunnel](#homelab-deployment--cloudflare-tunnel)
8. [AWS ECS Fargate Deployment](#aws-ecs-fargate-deployment)
9. [Ansible VM Provisioning](#ansible-vm-provisioning)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (async), Alembic, Python 3.11 |
| Database | PostgreSQL 15 |
| Cache | Redis 7 (optional — graceful no-op if `REDIS_URL` unset) |
| Frontend | Jinja2, HTMX, Tailwind CSS 3.4, FullCalendar v6, Chart.js v4 |
| Auth | Session cookies (itsdangerous), bcrypt passwords |
| Email | Resend API (falls back to console logging if key unset) |
| CAPTCHA | Cloudflare Turnstile |
| AI Chat | Ollama (dev/CPU) or Amazon Bedrock (prod) — optional |
| Container | Docker, Docker Compose |
| CI/CD | GitHub Actions → AWS ECR → ECS Fargate |

---

## Architecture & File Structure

```
ekorepetycje/
├── Dockerfile                        # Production image (python:3.11-slim)
├── docker-compose.yml                # Dev orchestration (web + db + redis; --profile ai for Ollama)
├── docker-entrypoint.sh              # Runs migrations + optional seed, then starts uvicorn
├── requirements.txt
├── alembic.ini
├── tailwind.config.js
├── package.json
│
├── .github/workflows/
│   ├── ci.yml                        # Test + Tailwind build on every PR
│   └── deploy.yml                    # Build → ECR → Alembic migrate → ECS deploy
│
├── scripts/
│   ├── seed_demo.py                  # Populate DB with demo teachers/students/events
│   ├── add_overlap_demo.py           # Add simultaneous events for overlap UI testing
│   └── backup_db.py                  # pg_dump → S3 backup script
│
├── alembic/
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 987a86e04ae0_*.py         # UnavailableBlocks
│       ├── 2816b3ee1935_*.py         # RecurringSeries + series_id on events
│       ├── da0d2e951ef7_*.py         # RecurringUnavailSeries
│       ├── 1d4d6c1fa5a5_*.py         # Teacher profile fields
│       ├── 698e615463d4_*.py         # reminder_sent_at on schedule_events
│       ├── 768151a670c1_*.py         # Composite indexes (teacher_id, start_time)
│       ├── d4260c02a08c_*.py         # EventChangeRequest table
│       └── 18f3e895b0f9_*.py         # Drop old reschedule_proposals table (head)
│
└── app/
    ├── main.py                       # FastAPI app entry point, router registration
    ├── core/
    │   ├── config.py                 # Settings (pydantic-settings, reads .env)
    │   ├── security.py               # hash_password / verify_password
    │   ├── auth.py                   # Session auth, require_admin/teacher/student
    │   ├── cache.py                  # Async Redis wrapper; graceful no-op when REDIS_URL=""
    │   └── templates.py              # Jinja2 environment singleton
    ├── db/
    │   ├── database.py               # Async engine + AsyncSession factory
    │   └── base.py                   # Declarative base (imports all models for Alembic)
    ├── models/
    │   ├── users.py                  # User (ADMIN / TEACHER / STUDENT)
    │   ├── offerings.py              # Offering (subject, price/h, teacher FK)
    │   ├── scheduling.py             # ScheduleEvent (SCHEDULED/COMPLETED/CANCELLED)
    │   ├── series.py                 # RecurringSeries (weekly/biweekly recurrence)
    │   ├── change_requests.py        # EventChangeRequest (bilateral reschedule proposals)
    │   ├── availability.py           # UnavailableBlock (one-off teacher/student block)
    │   └── unavail_series.py         # RecurringUnavailSeries (weekly unavailability)
    ├── schemas/                      # Pydantic v2 request/response models
    ├── services/
    │   ├── email.py                  # Resend API wrapper (logs if RESEND_API_KEY unset)
    │   ├── series.py                 # generate_events() — pure Python, no DB calls
    │   ├── unavailability.py         # generate_unavailable_blocks()
    │   ├── chat.py                   # LLM chat: OllamaChatService / BedrockChatService / DisabledChatService
    │   └── reminders.py              # Upcoming-session email reminder logic
    ├── api/
    │   ├── dependencies.py           # get_db, get_current_user
    │   ├── routes_landing.py         # Public pages (/, /contact, /nauczyciele, /przedmioty)
    │   ├── routes_admin.py           # /admin/* HTML routes
    │   ├── routes_teacher.py         # /teacher/* HTML routes
    │   ├── routes_student.py         # /student/* HTML routes
    │   ├── routes_auth.py            # /login, /logout
    │   ├── routes_profile.py         # /profile
    │   ├── routes_change_requests.py # /api/change-requests (bilateral proposals JSON API)
    │   └── routes_api.py             # JSON endpoints for FullCalendar, stats, CRUD
    └── static/
        ├── css/
        │   ├── input.css             # Tailwind source (custom keyframes, animations)
        │   └── style.css             # Compiled output (committed, served directly)
        ├── js/
        │   ├── admin_calendar.js     # FullCalendar admin: teacher colours, context menu
        │   ├── teacher_calendar.js   # FullCalendar teacher view
        │   ├── student_calendar.js   # FullCalendar student view (read-only)
        │   ├── series_panel.js       # Slide-in panel for creating/editing recurrence
        │   └── unavail_panel.js      # Slide-in panel for unavailability series
        └── templates/
            ├── base.html
            ├── landing/
            │   ├── index.html        # Hero, subjects, how-it-works, testimonials, pricing
            │   ├── teachers.html     # Full teacher listing
            │   ├── teacher_profile.html
            │   ├── subject_detail.html
            │   └── contact.html
            ├── admin/
            │   ├── dashboard.html    # KPI cards, Chart.js revenue/status charts
            │   ├── calendar.html     # Admin FullCalendar with teacher/student filter
            │   └── users.html        # User management table
            ├── teacher/
            │   ├── dashboard.html
            │   ├── calendar.html
            │   └── proposals.html    # Incoming (accept/reject) + outgoing (cancel) proposals
            ├── student/
            │   ├── dashboard.html
            │   ├── calendar.html
            │   └── proposals.html    # Same bilateral layout as teacher
            └── components/
                ├── navbar_admin.html
                ├── navbar_teacher.html
                ├── navbar_student.html
                ├── navbar_landing.html
                ├── chat_widget.html  # Floating AI chat FAB (disabled state if LLM_PROVIDER=disabled)
                ├── change_request_form.html
                ├── series_panel.html
                ├── unavail_panel.html
                └── offerings_list.html
```

---

## Database Schema

```
users
  id              UUID PK
  role            ENUM(admin, teacher, student)
  email           VARCHAR(255) UNIQUE
  hashed_password VARCHAR(255)
  full_name       VARCHAR(255)
  photo_url       VARCHAR(512) nullable
  bio             TEXT nullable
  specialties     VARCHAR(256) nullable
  created_at      TIMESTAMPTZ

offerings
  id                    UUID PK
  title                 VARCHAR(255)
  description           TEXT nullable
  base_price_per_hour   NUMERIC(10,2)
  teacher_id            UUID FK→users

schedule_events
  id                UUID PK
  title             VARCHAR(255)
  start_time        TIMESTAMPTZ  (indexed: teacher_id+start_time, student_id+start_time)
  end_time          TIMESTAMPTZ
  offering_id       UUID FK→offerings
  teacher_id        UUID FK→users
  student_id        UUID FK→users nullable
  series_id         UUID FK→recurring_series nullable (SET NULL on delete)
  status            ENUM(scheduled, completed, cancelled)
  reminder_sent_at  TIMESTAMPTZ nullable

event_change_requests
  id            UUID PK
  event_id      UUID FK→schedule_events CASCADE DELETE
  proposer_id   UUID FK→users
  responder_id  UUID FK→users
  new_start     TIMESTAMPTZ
  new_end       TIMESTAMPTZ
  note          VARCHAR(500) nullable
  status        ENUM(pending, accepted, rejected, cancelled)
  created_at    TIMESTAMPTZ
  resolved_at   TIMESTAMPTZ nullable
  (indexes on event_id, proposer_id, responder_id)

recurring_series
  id             UUID PK
  teacher_id     UUID FK→users
  student_id     UUID FK→users nullable
  offering_id    UUID FK→offerings
  title          VARCHAR(255)
  start_date     DATE
  interval_weeks INT  CHECK >= 1
  day_slots      JSONB  [{day:0-6, hour, minute, duration_minutes}]
  end_date       DATE nullable
  end_count      INT  nullable
  created_at     TIMESTAMPTZ

unavailable_blocks
  id         UUID PK
  user_id    UUID FK→users
  series_id  UUID FK→recurring_unavail_series nullable (SET NULL)
  start_time TIMESTAMPTZ
  end_time   TIMESTAMPTZ
  note       TEXT nullable

recurring_unavail_series
  id             UUID PK
  user_id        UUID FK→users
  day_of_week    INT (0=Mon … 6=Sun)
  start_time     TIME
  end_time       TIME
  valid_from     DATE
  valid_until    DATE nullable
  note           TEXT nullable
  created_at     TIMESTAMPTZ
```

Current Alembic head: `18f3e895b0f9`

---

## Feature Overview

### Landing page
- Scroll-reveal animations (IntersectionObserver, `prefers-reduced-motion` safe)
- Hero entrance with staggered delays
- Subjects, how-it-works, testimonials, pricing sections
- HTMX contact form with Resend email + Cloudflare Turnstile CAPTCHA
- Floating AI chat widget (animated green dot when active; grayed-out with contact-form link when `LLM_PROVIDER=disabled`)

### Authentication
- Session-cookie login for all three roles
- Role-based routing (wrong role → own dashboard, not 403)

### Admin panel
- **Dashboard**: 6 KPI cards (teachers, lessons/week, lessons/month, revenue this month with trend %, last month, 6-month average); Chart.js bar chart (6-month revenue); teacher breakdown table; status donut chart; 6 quick-action tiles
- **Calendar**: FullCalendar week/month/day view; teacher/student filter; date-range lazy loading (Redis-cached, 5 min TTL); teacher-colour-coded events; drag-to-reschedule; resize; right-click context menu; recurring series creation panel
- **Users**: HTMX-powered user table with inline role change, password reset, and teacher photo/profile management
- **Passive change-request badge** (HTMX polling, shows count of pending proposals)

### Teacher panel
- Personal calendar with their own events
- Recurring series creation/editing and one-off event management
- One-off + recurring unavailability management
- **Bilateral proposals**: propose reschedules to students; accept/reject incoming proposals from students
- Pending-count badge in navbar (HTMX polling every 60 s)

### Student panel
- Personal calendar (read-only events)
- One-off + recurring unavailability management
- **Bilateral proposals**: propose reschedules to teachers; accept/reject incoming proposals from teachers
- Pending-count badge in navbar

### AI Chat widget
- Floating FAB on the landing page for public visitors
- Streams responses via SSE (`text/event-stream`)
- `LLM_PROVIDER=disabled` (default) — widget visible, shows "Chatbot jest teraz niedostępny" with contact form link, no input
- `LLM_PROVIDER=ollama` — local Ollama server; start with `docker compose --profile ai up`
- `LLM_PROVIDER=bedrock` — Amazon Bedrock Claude; requires IAM instance role

### Redis caching
- Event window cache (`GET /api/events`) keyed by `events:t|s:{uuid}:{start}:{end}`, TTL 300 s
- Graceful no-op when `REDIS_URL` is empty (local dev without Redis)
- Cache invalidated on all event/series writes and on change-request acceptance

---

## Local Development

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for Tailwind hot-reload only)

### Start

```bash
git clone https://github.com/maciekgangus/Ekorepetycje.git
cd Ekorepetycje

cp .env.example .env   # review and fill in SECRET_KEY at minimum

# Start DB + Redis + web (hot-reload)
docker compose up --build
```

Migrations run automatically via `docker-entrypoint.sh`. App at **http://localhost:8000**.

### Load demo data

```bash
# Full demo dataset (5 teachers, 15 students, ~370 events)
docker compose exec web bash -c "cd /app && PYTHONPATH=/app python scripts/seed_demo.py"
```

### Demo credentials

| Role | Email | Password |
|---|---|---|
| Admin | admin@ekorepetycje.pl | admin123 |
| Teacher | anna@eko.pl | haslo123 |
| Student | marek@student.pl | haslo123 |

### Enable AI chatbot (optional)

```bash
# 1. Set in .env:
LLM_PROVIDER=ollama

# 2. Start with the AI profile (downloads ~2 GB model on first run):
docker compose --profile ai up --build
```

To use Amazon Bedrock in production set `LLM_PROVIDER=bedrock` and attach the
`bedrock:InvokeModelWithResponseStream` IAM policy to the instance role.

### Tailwind (standalone, outside Docker)

```bash
npm install
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css --watch
```

### Run tests

```bash
docker compose exec web pytest tests/ -v
```

### Generate a migration

```bash
docker compose exec web alembic revision --autogenerate -m "description"
docker compose exec web alembic upgrade head
```

---

## Environment Variables

Copy `.env.example` → `.env`. All defaults are safe for local Docker Compose development.

```dotenv
# Database (matches docker-compose.yml service names)
DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/ekorepetycje
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password          # change in production
POSTGRES_DB=ekorepetycje

# App
SECRET_KEY=<64-random-hex-chars>    # python -c "import secrets; print(secrets.token_hex(32))"
DEBUG=False

# Redis (event window cache)
# Leave blank to disable caching (tests, local dev without Docker)
REDIS_URL=redis://redis:6379/0

# Email (Resend) — leave blank to fall back to console logging
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL=Ekorepetycje <onboarding@resend.dev>
RESEND_TO_EMAIL=kontakt@ekorepetycje.pl

# AI Chat
# "disabled" → chat widget shows unavailable message (default, no extra services)
# "ollama"   → local Ollama; requires docker compose --profile ai up
# "bedrock"  → Amazon Bedrock Claude; requires IAM role
LLM_PROVIDER=disabled
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2:3b
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0

# Cloudflare Turnstile (CAPTCHA) — test keys always pass locally
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
```

---

## Homelab Deployment + Cloudflare Tunnel

Recommended for running 24/7 on your own hardware, accessible from the internet without opening ports.

### Architecture

```
Internet ──► Cloudflare CDN ──► cloudflared tunnel ──► localhost:8000 (Docker)
                                        │
                              runs on your homelab VM
```

### Step 1 — Provision the VM

Use the Ansible playbook in `deploy/ansible/` or manually:

```bash
# Ubuntu 22.04 / Debian 12
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ca-certificates gnupg

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose plugin
sudo apt install -y docker-compose-plugin
docker compose version   # should print v2.x
```

### Step 2 — Clone and configure

```bash
git clone https://github.com/maciekgangus/Ekorepetycje.git /opt/ekorepetycje
cd /opt/ekorepetycje

cp .env.example .env
nano .env   # set SECRET_KEY, RESEND_API_KEY, POSTGRES_PASSWORD, TURNSTILE_SECRET_KEY
```

### Step 3 — Production docker-compose override

Create `/opt/ekorepetycje/docker-compose.prod.yml`:

```yaml
services:
  db:
    restart: always

  redis:
    restart: always

  web:
    restart: always
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    volumes: []   # serve from built image, not mounted source

volumes:
  postgres_data:
    external: true
  redis_data:
    external: true
```

```bash
docker volume create postgres_data
docker volume create redis_data

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec web alembic upgrade head
```

### Step 4 — Cloudflare Tunnel

#### 4a. Install cloudflared

```bash
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared
```

#### 4b. Authenticate and create tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create ekorepetycje
```

#### 4c. Tunnel config

```bash
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <YOUR_TUNNEL_UUID>
credentials-file: /root/.cloudflared/<YOUR_TUNNEL_UUID>.json

ingress:
  - hostname: ekorepetycje.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF
```

#### 4d. DNS + systemd

```bash
cloudflared tunnel route dns ekorepetycje ekorepetycje.yourdomain.com

sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

App is live at `https://ekorepetycje.yourdomain.com` with automatic HTTPS.

### Step 5 — Auto-update script (optional)

```bash
cat > /opt/ekorepetycje/deploy.sh << 'EOF'
#!/bin/bash
set -e
cd /opt/ekorepetycje
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec -T web alembic upgrade head
echo "Deploy complete at $(date)"
EOF
chmod +x /opt/ekorepetycje/deploy.sh
```

### Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```

---

## AWS ECS Fargate Deployment

The repository ships with `.github/workflows/deploy.yml`.

### Pipeline overview

```
push to main
    │
    ├─► [1] pytest + alembic migrate (test DB)
    ├─► [2] npx tailwindcss build → docker build → push to ECR
    ├─► [3] alembic upgrade head (one-off ECS Fargate task against prod DB)
    └─► [4] update ECS task definition → rolling deploy → wait for stability
```

### Required AWS resources

| Resource | Name |
|---|---|
| ECR repository | `ekorepetycje` |
| ECS cluster | `ekorepetycje-cluster` |
| ECS service | `ekorepetycje-web` |
| ECS task definition | `ekorepetycje` (container name: `web`) |
| RDS PostgreSQL 15 | in private subnet |
| ElastiCache Redis (optional) | in private subnet |
| ALB + HTTPS listener | with ACM certificate |

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user key (ECR push + ECS deploy) |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret |
| `ECS_PRIVATE_SUBNET_IDS` | Comma-separated subnet IDs |
| `ECS_SECURITY_GROUP_ID` | SG allowing DB + Redis access |

### ECS task definition environment variables

```
DATABASE_URL=postgresql+asyncpg://user:pass@rds-endpoint:5432/ekorepetycje
SECRET_KEY=<64-char random>
REDIS_URL=redis://elasticache-endpoint:6379/0
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
TURNSTILE_SECRET_KEY=0x4AAAAAAA...
LLM_PROVIDER=bedrock              # or disabled
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
AWS_DEFAULT_REGION=us-east-1      # required for Bedrock
```

For Bedrock: attach `bedrock:InvokeModelWithResponseStream` to the ECS task IAM role — no extra API keys needed.

### Rollback

```bash
aws ecs list-task-definitions --family-prefix ekorepetycje
aws ecs update-service \
  --cluster ekorepetycje-cluster \
  --service ekorepetycje-web \
  --task-definition ekorepetycje:<PREVIOUS_REVISION>
```

---

## Ansible VM Provisioning

`deploy/ansible/` contains a playbook that:

- Installs Docker + Docker Compose plugin
- Installs `cloudflared`
- Clones the repo to `/opt/ekorepetycje`
- Writes `.env` from vault variables
- Creates and starts the production Docker Compose stack
- Applies Alembic migrations
- Configures cloudflared as a systemd service
- Configures UFW (SSH only inbound)

### Usage

```bash
cd deploy/ansible

cp inventory.yml.example inventory.yml
nano inventory.yml

ansible-vault create group_vars/all/vault.yml

# Dry-run
ansible-playbook playbook.yml --check --diff -i inventory.yml

# Full provision
ansible-playbook playbook.yml -i inventory.yml --ask-vault-pass
```

### Re-deploy after code changes

```bash
ansible-playbook playbook.yml -i inventory.yml --ask-vault-pass --tags deploy
```
