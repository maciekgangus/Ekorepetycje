# Ekorepetycje

A modern tutoring platform MVP — FastAPI backend, Jinja2/HTMX frontend, FullCalendar scheduling, PostgreSQL. Built with a Vercel/Next.js dark aesthetic.

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
| Frontend | Jinja2, HTMX, Tailwind CSS, FullCalendar v6, Chart.js v4 |
| Auth | Session cookies (itsdangerous), bcrypt passwords |
| Email | Resend API |
| CAPTCHA | Cloudflare Turnstile |
| Container | Docker, Docker Compose |
| CI/CD | GitHub Actions → AWS ECR → ECS Fargate |

---

## Architecture & File Structure

```
ekorepetycje/
├── Dockerfile                        # Production image (python:3.11-slim)
├── docker-compose.yml                # Dev orchestration (web + db + css watcher)
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
│   └── add_overlap_demo.py           # Add 5 simultaneous events for UI testing
│
├── alembic/
│   └── versions/                     # Auto-generated migration files
│
└── app/
    ├── main.py                       # FastAPI app entry point, router registration
    ├── core/
    │   ├── config.py                 # Settings (pydantic-settings, reads .env)
    │   ├── security.py               # hash_password / verify_password
    │   ├── auth.py                   # Session auth, require_admin/teacher/student
    │   └── templates.py             # Jinja2 environment singleton
    ├── db/
    │   ├── database.py               # Async engine + AsyncSession factory
    │   └── base.py                   # Declarative base
    ├── models/
    │   ├── users.py                  # User (ADMIN / TEACHER / STUDENT)
    │   ├── offerings.py              # Offering (subject, price/h, teacher FK)
    │   ├── scheduling.py             # ScheduleEvent (SCHEDULED/COMPLETED/CANCELLED)
    │   ├── series.py                 # RecurringSeries (weekly/biweekly recurrence)
    │   ├── proposals.py              # RescheduleProposal (teacher → admin)
    │   ├── availability.py           # UnavailableBlock (one-off block)
    │   └── unavail_series.py         # RecurringUnavailSeries (weekly unavailability)
    ├── schemas/                      # Pydantic request/response models
    ├── services/
    │   ├── email.py                  # Resend API wrapper
    │   └── series.py                 # Event generation from RecurringSeries rules
    ├── api/
    │   ├── dependencies.py           # get_db, get_current_user
    │   ├── routes_landing.py         # Public pages (/, /contact, HTMX fragments)
    │   ├── routes_admin.py           # /admin/* HTML routes
    │   ├── routes_teacher.py         # /teacher/* HTML routes
    │   ├── routes_student.py         # /student/* HTML routes
    │   ├── routes_auth.py            # /login, /logout
    │   ├── routes_profile.py         # /profile
    │   └── routes_api.py             # JSON endpoints for FullCalendar + dashboard
    └── static/
        ├── css/
        │   ├── input.css             # Tailwind source (custom keyframes, animations)
        │   └── style.css             # Compiled output (committed, served directly)
        ├── js/
        │   ├── admin_calendar.js     # FullCalendar admin: teacher colours, context menu
        │   ├── teacher_calendar.js   # FullCalendar teacher view
        │   ├── student_calendar.js   # FullCalendar student view (read + unavailability)
        │   ├── series_panel.js       # Slide-in panel for creating/editing recurrence
        │   └── unavail_panel.js      # Slide-in panel for unavailability series
        └── templates/
            ├── base.html
            ├── landing/
            │   └── index.html        # Hero, subjects, how-it-works, testimonials, pricing
            ├── admin/
            │   ├── dashboard.html    # KPI cards, Chart.js revenue/status charts
            │   └── calendar.html     # Admin FullCalendar with teacher/student filter
            ├── teacher/
            │   ├── dashboard.html
            │   └── calendar.html
            ├── student/
            │   ├── dashboard.html
            │   └── calendar.html
            └── components/
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
  id           UUID PK
  title        VARCHAR(255)
  start_time   TIMESTAMPTZ
  end_time     TIMESTAMPTZ
  offering_id  UUID FK→offerings
  teacher_id   UUID FK→users
  student_id   UUID FK→users nullable
  series_id    UUID FK→recurring_series nullable (SET NULL on delete)
  status       ENUM(scheduled, completed, cancelled)

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

reschedule_proposals
  id           UUID PK
  event_id     UUID FK→schedule_events
  proposed_by  UUID FK→users
  new_start    TIMESTAMPTZ
  new_end      TIMESTAMPTZ
  status       ENUM(pending, approved, rejected)
  created_at   TIMESTAMPTZ

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

---

## Feature Overview

### Landing page
- Scroll-reveal animations (IntersectionObserver, `prefers-reduced-motion` safe)
- Hero entrance with staggered delays
- Subjects, how-it-works, testimonials, pricing sections
- HTMX contact form with Resend email + Cloudflare Turnstile CAPTCHA

### Authentication
- Session-cookie login for all three roles
- Role-based routing (wrong role → own dashboard, not 403)

### Admin panel
- **Dashboard**: 6 KPI cards (teachers, lessons/week, lessons/month, revenue this month with trend %, last month, 6-month average); Chart.js bar chart (6-month revenue); teacher breakdown table; status donut chart; 6 quick-action tiles
- **Calendar**: FullCalendar week/month/day view; teacher/student filter dropdown; teacher-colour-coded events (5-color palette, stable UUID hash); drag-to-reschedule; resize; right-click context menu (edit, status change, delete series); edit modal; recurring series creation panel

### Teacher panel
- Personal calendar with their own events
- Recurring series creation/editing
- One-off + recurring unavailability management
- Reschedule proposal submission

### Student panel
- Personal calendar (read-only events)
- One-off + recurring unavailability management

---

## Local Development

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for Tailwind hot-reload)

### Start

```bash
git clone <repo-url>
cd ekorepetycje

cp .env.example .env          # fill in SECRET_KEY, RESEND_API_KEY, etc.

# Start DB + web (hot-reload)
docker-compose up --build

# In a separate terminal — Tailwind watcher
docker-compose --profile dev up css
```

App runs at **http://localhost:8000**

### Apply migrations

```bash
docker-compose exec web alembic upgrade head
```

### Load demo data

```bash
# Full demo dataset (5 teachers, 15 students, ~370 events)
docker-compose exec web bash -c "cd /app && PYTHONPATH=/app python scripts/seed_demo.py"

# Add 5 simultaneous Saturday events for overlap testing
docker-compose exec web bash -c "cd /app && PYTHONPATH=/app python scripts/add_overlap_demo.py"
```

### Demo credentials

| Role | Email | Password |
|---|---|---|
| Admin | admin@ekorepetycje.pl | admin123 |
| Teacher | anna@eko.pl | haslo123 |
| Student | marek@student.pl | haslo123 |

### Tailwind (standalone, outside Docker)

```bash
npm install
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css --watch
```

### Run tests

```bash
docker-compose exec web pytest tests/ -v
```

---

## Environment Variables

Copy `.env.example` → `.env` and fill in:

```dotenv
# Database (matches docker-compose.yml)
DATABASE_URL=postgresql+asyncpg://postgres:password@db:5432/ekorepetycje
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password          # change in production
POSTGRES_DB=ekorepetycje

# App
SECRET_KEY=change-me-to-64-random-chars   # used for session signing
DEBUG=False                               # True enables uvicorn --reload

# Email (Resend)
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL=noreply@yourdomain.com

# Cloudflare Turnstile (contact form CAPTCHA)
TURNSTILE_SECRET_KEY=0x4AAAAAAA...
```

Generate a secure SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Homelab Deployment + Cloudflare Tunnel

This is the recommended path for running the app 24/7 on your own hardware, accessible from the internet without opening ports or exposing your home IP.

### Architecture

```
Internet ──► Cloudflare CDN ──► cloudflared tunnel ──► localhost:8000 (Docker)
                                        │
                              runs on your homelab VM
```

No port-forwarding, no reverse proxy setup, no TLS certificates to manage — Cloudflare handles all of it.

### Step 1 — Provision the VM

Use the Ansible playbook in `deploy/ansible/` (see [Ansible VM Provisioning](#ansible-vm-provisioning)) or do it manually:

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

### Step 2 — Clone the repo and configure

```bash
git clone https://github.com/your-org/ekorepetycje.git /opt/ekorepetycje
cd /opt/ekorepetycje

cp .env.example .env
nano .env          # set SECRET_KEY, RESEND_API_KEY, POSTGRES_PASSWORD, TURNSTILE_SECRET_KEY
```

### Step 3 — Production docker-compose override

Create `/opt/ekorepetycje/docker-compose.prod.yml`:

```yaml
services:
  db:
    restart: always

  web:
    restart: always
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    # Remove the dev volume mounts — serve from the built image
    volumes:
      - postgres_data:/var/lib/postgresql/data   # keep DB volume

volumes:
  postgres_data:
    external: true
```

Start in production mode:

```bash
# Create the named volume once
docker volume create postgres_data

# Build and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Apply migrations
docker compose exec web alembic upgrade head
```

Check logs:
```bash
docker compose logs -f web
```

### Step 4 — Cloudflare Tunnel

#### 4a. Install cloudflared

```bash
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared
```

#### 4b. Authenticate

```bash
cloudflared tunnel login
# Opens a browser — authorize for your Cloudflare account
```

#### 4c. Create the tunnel

```bash
cloudflared tunnel create ekorepetycje
# Note the tunnel UUID printed, e.g.: abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

#### 4d. Create tunnel config

```bash
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <YOUR_TUNNEL_UUID>
credentials-file: /root/.cloudflared/<YOUR_TUNNEL_UUID>.json

ingress:
  - hostname: ekorepetycje.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF
```

#### 4e. Create DNS record

```bash
cloudflared tunnel route dns ekorepetycje ekorepetycje.yourdomain.com
```

This creates a CNAME in your Cloudflare DNS pointing to the tunnel — no IP address needed.

#### 4f. Run tunnel as a systemd service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

Your app is now live at `https://ekorepetycje.yourdomain.com` with automatic HTTPS from Cloudflare.

### Step 5 — Auto-update on git push (optional)

Add a deploy script at `/opt/ekorepetycje/deploy.sh`:

```bash
#!/bin/bash
set -e
cd /opt/ekorepetycje
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec -T web alembic upgrade head
echo "Deploy complete at $(date)"
```

```bash
chmod +x /opt/ekorepetycje/deploy.sh
```

Trigger manually, via cron, or via a GitHub Actions webhook.

### Firewall

The app only needs outbound internet access for Cloudflare tunnel — no inbound ports required. If you want UFW:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```

---

## AWS ECS Fargate Deployment

The repository ships with a full GitHub Actions CI/CD pipeline in `.github/workflows/deploy.yml`.

### Pipeline overview

```
push to main
    │
    ├─► [1] pytest + alembic migrate (test DB)
    ├─► [2] npx tailwindcss build → docker build → push to ECR
    ├─► [3] alembic upgrade head (one-off ECS Fargate task against prod DB)
    └─► [4] update ECS task definition → rolling deploy → wait for stability
```

### AWS infrastructure required

You must create these resources before the first deploy (Terraform, CDK, or manual console):

| Resource | Name |
|---|---|
| ECR repository | `ekorepetycje` |
| ECS cluster | `ekorepetycje-cluster` |
| ECS service | `ekorepetycje-web` |
| ECS task definition | `ekorepetycje` (container name: `web`) |
| RDS PostgreSQL 15 | in private subnet |
| ALB + HTTPS listener | with ACM certificate |
| VPC private subnets | for ECS tasks |
| Security groups | ECS → RDS on 5432, ALB → ECS on 8000 |

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user key (ECR push + ECS deploy permissions) |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret |
| `ECS_PRIVATE_SUBNET_IDS` | Comma-separated: `subnet-xxx,subnet-yyy` |
| `ECS_SECURITY_GROUP_ID` | SG allowing DB access |

### ECS task definition environment variables

Set these as task-definition secrets (from AWS Secrets Manager or Parameter Store):

```
DATABASE_URL=postgresql+asyncpg://user:pass@rds-endpoint:5432/ekorepetycje
SECRET_KEY=<64-char random>
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=noreply@yourdomain.com
TURNSTILE_SECRET_KEY=0x4AAAAAAA...
```

### Deploy

Push to `main` — the pipeline runs automatically. Monitor at:
```
GitHub → Actions → "Deploy to AWS"
```

### Rollback

```bash
# List task definition revisions
aws ecs list-task-definitions --family-prefix ekorepetycje

# Force service to use a previous revision
aws ecs update-service \
  --cluster ekorepetycje-cluster \
  --service ekorepetycje-web \
  --task-definition ekorepetycje:<PREVIOUS_REVISION>
```

---

## Ansible VM Provisioning

The `deploy/ansible/` directory contains a full Ansible role that:

- Installs Docker + Docker Compose plugin
- Installs `cloudflared`
- Clones the repo to `/opt/ekorepetycje`
- Writes `.env` from vault variables
- Creates and starts the production Docker Compose stack
- Applies Alembic migrations
- Configures cloudflared as a systemd service
- Configures UFW firewall (SSH only inbound)

### Usage

```bash
cd deploy/ansible

# Copy and fill in your inventory
cp inventory.yml.example inventory.yml
nano inventory.yml

# Encrypt secrets with ansible-vault
ansible-vault create group_vars/all/vault.yml
# Fill in vault variables (see defaults/main.yml for the full list)

# Dry-run first
ansible-playbook playbook.yml --check --diff -i inventory.yml

# Full provision
ansible-playbook playbook.yml -i inventory.yml --ask-vault-pass
```

### Re-deploy after code changes

```bash
ansible-playbook playbook.yml -i inventory.yml --ask-vault-pass --tags deploy
```
