# Landing Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the landing page layout, simplify subject cards, add subject detail pages, add a live teacher section driven by the DB, and wire teacher profile editing into both the teacher dashboard and admin panel.

**Architecture:** DB-first (User model gains `photo_url`, `bio`, `specialties`, `created_at`), then backend routes in `routes_landing.py` and `routes_api.py`, then Jinja2 templates last. Each task is independently releasable.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Jinja2, HTMX, Tailwind CSS, Pillow (image processing), pytest + httpx for tests.

---

## File Map

| File | Action | What it does |
|------|--------|--------------|
| `app/models/users.py` | Modify | Add `photo_url`, `bio`, `specialties`, `created_at` |
| `app/db/base.py` | Check only | Already imports User; no change needed |
| `alembic/versions/<hash>_add_teacher_profile_fields.py` | Create | Migration for 4 new columns |
| `app/api/routes_landing.py` | Modify | Add `/przedmioty/{slug}`, `/nauczyciele`, `/nauczyciele/{id}`; update `/` to pass `featured_teachers` |
| `app/api/routes_api.py` | Modify | Add photo upload + profile PATCH endpoints |
| `app/templates/landing/index.html` | Modify | Hero max-width, subjects rename/simplify, remove filter tabs, add teacher section |
| `app/templates/landing/subject_detail.html` | Create | Subject detail page (static description + live teacher grid) |
| `app/templates/landing/teachers.html` | Create | All teachers list page |
| `app/templates/landing/teacher_profile.html` | Create | Individual teacher profile page |
| `app/templates/teacher/dashboard.html` | Modify | Add profile edit card |
| `app/templates/admin/users.html` | Modify | Add "Edytuj profil" per teacher row |
| `app/static/img/teachers/` | Create dir | Uploaded teacher photos (created at runtime) |
| `tests/test_landing_redesign.py` | Create | Tests for new routes |
| `tests/test_teacher_profile_api.py` | Create | Tests for upload + PATCH endpoints |

---

## Task 1: User Model + Migration

**Files:**
- Modify: `app/models/users.py`
- Create: `alembic/versions/<hash>_add_teacher_profile_fields.py` (via autogenerate)

- [ ] **Step 1: Write the failing test**

Create `tests/test_landing_redesign.py`:

```python
"""Tests for the landing page redesign routes."""
import pytest
from httpx import AsyncClient, ASGITransport


async def test_user_model_has_profile_fields():
    """User model must have photo_url, bio, specialties, created_at."""
    from app.models.users import User
    assert hasattr(User, "photo_url")
    assert hasattr(User, "bio")
    assert hasattr(User, "specialties")
    assert hasattr(User, "created_at")
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_user_model_has_profile_fields -v
```
Expected: FAILED — `AssertionError` on `photo_url`

- [ ] **Step 3: Add profile fields to the User model**

Edit `app/models/users.py`. Add imports at the top (after existing imports):
```python
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
```

Add these four columns after `full_name`:
```python
photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
bio: Mapped[str | None] = mapped_column(Text, nullable=True)
specialties: Mapped[str | None] = mapped_column(String(256), nullable=True)
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_user_model_has_profile_fields -v
```
Expected: PASSED

- [ ] **Step 5: Generate and inspect migration**

```bash
docker-compose exec web alembic revision --autogenerate -m "add teacher profile fields"
```

Open the generated file in `alembic/versions/`. It should have:
- `op.add_column('users', sa.Column('photo_url', sa.String(512), nullable=True))`
- `op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))`
- `op.add_column('users', sa.Column('specialties', sa.String(256), nullable=True))`
- `op.add_column('users', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))`

**Important:** SQLAlchemy autogenerate may generate `created_at` as `nullable=True` first. If so, manually edit the migration to:
1. Add column as `nullable=True` with `server_default`
2. Add `op.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")`
3. Then `op.alter_column('users', 'created_at', nullable=False)`

- [ ] **Step 6: Run the migration**

```bash
docker-compose exec web alembic upgrade head
```
Expected: no errors

- [ ] **Step 7: Verify columns in DB**

```bash
docker-compose exec db psql -U postgres -d ekorepetycje -c "\d users"
```
Expected: `photo_url`, `bio`, `specialties`, `created_at` columns visible

- [ ] **Step 8: Commit**

```bash
git add app/models/users.py alembic/versions/ tests/test_landing_redesign.py
git commit -m "feat(db): add teacher profile fields to User model"
```

---

## Task 2: Landing Hero + Subjects Fix (Pure Frontend)

**Files:**
- Modify: `app/templates/landing/index.html`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_landing_redesign.py`:

```python
async def test_landing_page_no_ampersand_in_subjects():
    """Subject card headings must not contain & character."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    # Check subject names use 'i' not '&'
    assert "Matematyka i Fizyka" in r.text
    assert "Informatyka i IT" in r.text
    # Filter tabs should be gone
    assert 'hx-get="/subjects?level=' not in r.text


async def test_landing_hero_has_max_width_wrapper():
    """Hero inner content must be wrapped in a max-width container."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert "max-w-7xl" in r.text
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_landing_page_no_ampersand_in_subjects tests/test_landing_redesign.py::test_landing_hero_has_max_width_wrapper -v
```
Expected: both FAILED

- [ ] **Step 3: Edit `app/templates/landing/index.html`**

**3a. Hero max-width fix** — on line 14, change:
```html
<section id="hero" class="min-h-screen pt-16 px-6 grid grid-cols-1 lg:grid-cols-5 gap-0 items-stretch">
```
to:
```html
<section id="hero" class="min-h-screen pt-16 px-6">
<div class="max-w-7xl mx-auto w-full h-full grid grid-cols-1 lg:grid-cols-5 gap-0 items-stretch min-h-[calc(100vh-4rem)]">
```
And close with `</div>` before `</section>` (after line 85's `</div>`).

**3b. Remove filter tabs block** — delete lines 99–136 (the `<!-- Filter tabs -->` div entirely, including the `<div class="flex flex-wrap gap-2 mb-10 ...">` block and the `htmx-indicator` span). The `#subjects-grid` div that follows stays.

**3c. Rename subjects and add links** — in the subjects grid (lines ~139–206):

Replace `Matematyka &amp; Fizyka` with `Matematyka i Fizyka`:
```html
<h3 class="font-serif text-xl font-semibold text-ink mb-3">
    Matematyka i Fizyka
</h3>
```

Replace `Programowanie &amp; IT` with `Informatyka i IT`:
```html
<h3 class="font-serif text-xl font-semibold text-ink mb-3">
    Informatyka i IT
</h3>
```

**3d. Add "Dowiedz się więcej" links** — at the end of each subject card div, after the `<div class="flex flex-wrap gap-2">` badges block, add:

For Matematyka i Fizyka:
```html
<a href="/przedmioty/matematyka"
   class="mt-4 inline-flex items-center gap-1 text-xs text-navy font-medium hover:underline">
    Dowiedz się więcej
    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/>
    </svg>
</a>
```

For Informatyka i IT: link to `/przedmioty/informatyka`
For Języki Obce: link to `/przedmioty/jezyki-obce`

- [ ] **Step 4: Run tests**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_landing_page_no_ampersand_in_subjects tests/test_landing_redesign.py::test_landing_hero_has_max_width_wrapper -v
```
Expected: both PASSED

- [ ] **Step 5: Rebuild Tailwind (max-w-7xl may need recompile)**

```bash
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css
```

- [ ] **Step 6: Visual check**

```bash
# Navigate to http://localhost:8000 and verify:
# - Hero content is centered with margins on wide screen
# - Subject cards show "Matematyka i Fizyka", "Informatyka i IT"
# - No filter tabs
# - "Dowiedz się więcej →" links at bottom of each card
```

- [ ] **Step 7: Commit**

```bash
git add app/templates/landing/index.html app/static/css/style.css
git commit -m "feat(ui): fix hero max-width, simplify subject cards, remove filter tabs"
```

---

## Task 3: Subject Detail Pages

**Files:**
- Modify: `app/api/routes_landing.py`
- Create: `app/templates/landing/subject_detail.html`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_landing_redesign.py`:

```python
async def test_subject_detail_matematyka_returns_200():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/przedmioty/matematyka")
    assert r.status_code == 200
    assert "Matematyka" in r.text


async def test_subject_detail_informatyka_returns_200():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/przedmioty/informatyka")
    assert r.status_code == 200
    assert "Informatyka" in r.text


async def test_subject_detail_jezyki_returns_200():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/przedmioty/jezyki-obce")
    assert r.status_code == 200
    assert "Języki" in r.text


async def test_subject_detail_unknown_slug_returns_404():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/przedmioty/fizyka")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py -k "subject_detail" -v
```
Expected: all FAILED (404 or connection error)

- [ ] **Step 3: Update `app/api/routes_landing.py`**

Add new imports at the top:
```python
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException
from app.api.dependencies import get_db
from app.models.users import User, UserRole
```

Add these routes after the existing `/contact/submit` endpoint:

```python
_SUBJECT_KEYWORDS: dict[str, str] = {
    "matematyka": "Matematyka",
    "informatyka": "Informatyka",
    "jezyki-obce": "Języki",
}


@router.get("/przedmioty/{slug}", response_class=HTMLResponse)
async def subject_detail(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render a subject detail page with static description and live teacher list."""
    if slug not in _SUBJECT_KEYWORDS:
        raise HTTPException(status_code=404, detail="Subject not found")
    keyword = _SUBJECT_KEYWORDS[slug]
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .where(User.specialties.ilike(f"%{keyword}%"))
        .order_by(User.created_at.asc())
    )
    teachers = result.scalars().all()
    return templates.TemplateResponse(
        "landing/subject_detail.html",
        {"request": request, "subject": slug, "keyword": keyword, "teachers": teachers},
    )
```

- [ ] **Step 4: Create `app/templates/landing/subject_detail.html`**

```html
{% extends "base.html" %}

{% block html_attrs %}{% endblock %}
{% block body_attrs %}class="bg-cream text-ink font-sans antialiased min-h-screen"{% endblock %}
{% block navbar %}{% include "components/navbar_landing.html" %}{% endblock %}

{% block title %}
{% if subject == "matematyka" %}Matematyka i Fizyka{% elif subject == "informatyka" %}Informatyka i IT{% else %}Języki Obce{% endif %}
 — Ekorepetycje
{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-4 sm:px-6 max-w-7xl mx-auto">

    <!-- Breadcrumb -->
    <nav class="mb-10 text-xs text-ink/40 tracking-wide">
        <a href="/" class="hover:text-navy transition-colors">Strona główna</a>
        <span class="mx-2">·</span>
        <a href="/#przedmioty" class="hover:text-navy transition-colors">Przedmioty</a>
        <span class="mx-2">·</span>
        <span class="text-ink/60">{{ keyword }}</span>
    </nav>

    <!-- Static description -->
    <div class="max-w-3xl mb-20">
        <p class="text-xs font-medium text-ink/40 tracking-[0.2em] uppercase mb-4">Oferta</p>

        {% if subject == "matematyka" %}
        <h1 class="font-serif text-4xl md:text-5xl font-bold text-ink mb-8">Matematyka i Fizyka</h1>
        <div class="space-y-5 text-ink/70 leading-relaxed">
            <p>Oferujemy korepetycje z matematyki i fizyki dla uczniów szkół podstawowych, licealistów oraz
            studentów. Nasi nauczyciele specjalizują się w przygotowaniu do egzaminów — od matury
            podstawowej po rozszerzoną — i olimpiad przedmiotowych.</p>
            <p>Każde zajęcia zaczynamy od diagnozy — identyfikujemy luki w wiedzy i dopasowujemy tempo
            do indywidualnych potrzeb. Typowe obszary: algebra liniowa, rachunek różniczkowy i całkowy,
            geometria analityczna, mechanika klasyczna i elektrodynamika.</p>
            <p>Uczniowie przygotowujący się do matury rozszerzonej osiągają u nas średnio o 18 punktów
            procentowych więcej niż przed rozpoczęciem korepetycji. Używamy sprawdzonych metod
            rozwiązywania zadań i arkuszy z poprzednich lat.</p>
            <p>Zajęcia odbywają się online lub stacjonarnie w Warszawie — elastyczny grafik dopasowany
            do planu szkolnego i semestralnego.</p>
        </div>
        {% elif subject == "informatyka" %}
        <h1 class="font-serif text-4xl md:text-5xl font-bold text-ink mb-8">Informatyka i IT</h1>
        <div class="space-y-5 text-ink/70 leading-relaxed">
            <p>Prowadzimy korepetycje z informatyki, programowania i algorytmiki — od poziomu licealnego
            po studia inżynierskie. Przygotowujemy do matury z informatyki, rozmów kwalifikacyjnych
            w branży IT oraz egzaminów semestralnych.</p>
            <p>Obejmujemy języki programowania: Python, JavaScript, C++, Java. Uczymy myślenia
            algorytmicznego — złożoność obliczeniowa, struktury danych, programowanie dynamiczne —
            a nie tylko składni. Każdy uczeń pracuje na własnych projektach.</p>
            <p>Dla studentów oferujemy wsparcie przy projektach zaliczeniowych, analizie kodu
            i przygotowaniu do kolokwiów z algorytmów i programowania obiektowego.</p>
            <p>Wszystkie zajęcia online — co daje dostęp do środowisk developerskich i współdzielenia
            ekranu w czasie rzeczywistym.</p>
        </div>
        {% else %}
        <h1 class="font-serif text-4xl md:text-5xl font-bold text-ink mb-8">Języki Obce</h1>
        <div class="space-y-5 text-ink/70 leading-relaxed">
            <p>Oferujemy korepetycje z angielskiego, niemieckiego i hiszpańskiego na wszystkich poziomach
            zaawansowania — od A1 do C2. Specjalizujemy się w przygotowaniu do egzaminów
            Cambridge (FCE, CAE, CPE), IELTS, TOEFL oraz matur językowych.</p>
            <p>Zajęcia skupiają się na praktycznym użyciu języka: konwersacje, pisanie, rozumienie
            ze słuchu i czytanie. Nie uczymy „szkolnego" angielskiego — uczymy języka, którym
            mówi się w pracy, na uczelni i w podróży.</p>
            <p>Nasi lektorzy posiadają certyfikaty CELTA i DELTA, a część z nich to native speakerzy
            lub osoby z długoletnim doświadczeniem za granicą. Każdy kurs poprzedzamy testem
            poziomującym.</p>
            <p>Elastyczny grafik — zajęcia online lub w Warszawie, w weekendy i wieczorami.</p>
        </div>
        {% endif %}
    </div>

    <!-- Dynamic teacher grid -->
    {% if teachers %}
    <div class="border-t border-ink/10 pt-16">
        <p class="text-xs font-medium text-ink/40 tracking-[0.2em] uppercase mb-4">Zespół</p>
        <h2 class="font-serif text-3xl font-bold text-ink mb-10">Nauczyciele tego przedmiotu</h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {% for teacher in teachers %}
            <a href="/nauczyciele/{{ teacher.id }}"
               class="border border-ink/10 p-6 hover:border-navy/30 hover:bg-navy/5 transition-colors group block">
                <div class="flex items-center gap-4 mb-4">
                    {% if teacher.photo_url %}
                    <img src="{{ teacher.photo_url }}" alt="{{ teacher.full_name }}"
                         class="w-14 h-14 object-cover flex-shrink-0">
                    {% else %}
                    <div class="w-14 h-14 bg-navy flex items-center justify-center flex-shrink-0">
                        <span class="text-cream font-serif text-lg font-bold">
                            {{ teacher.full_name[:2].upper() }}
                        </span>
                    </div>
                    {% endif %}
                    <div>
                        <p class="font-semibold text-ink group-hover:text-navy transition-colors">{{ teacher.full_name }}</p>
                        {% if teacher.specialties %}
                        <p class="text-xs text-navy/70 mt-0.5">{{ teacher.specialties }}</p>
                        {% endif %}
                    </div>
                </div>
                {% if teacher.bio %}
                <p class="text-sm text-ink/60 leading-relaxed">
                    {{ teacher.bio[:120] }}{% if teacher.bio|length > 120 %}…{% endif %}
                </p>
                {% endif %}
            </a>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- CTA -->
    <div class="mt-20 border-t border-ink/10 pt-16 text-center">
        <p class="text-ink/60 mb-6">Gotowy, żeby zacząć? Pierwsza konsultacja jest bezpłatna.</p>
        <a href="/#kontakt"
           class="inline-flex items-center gap-2 bg-navy hover:bg-navy/90 text-cream font-medium px-8 py-3.5 transition-colors text-sm tracking-wide">
            Umów bezpłatną konsultację
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 8l4 4m0 0l-4 4m4-4H3"/>
            </svg>
        </a>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py -k "subject_detail" -v
```
Expected: all 4 PASSED

- [ ] **Step 6: Rebuild Tailwind**

```bash
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css
```

- [ ] **Step 7: Commit**

```bash
git add app/api/routes_landing.py app/templates/landing/subject_detail.html app/static/css/style.css
git commit -m "feat(landing): add subject detail pages with static content and live teacher grid"
```

---

## Task 4: Teacher Section on Main Page

**Files:**
- Modify: `app/api/routes_landing.py`
- Modify: `app/templates/landing/index.html`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_landing_redesign.py`:

```python
async def test_landing_page_teacher_section_hidden_when_no_teachers():
    """Teacher section must be absent when no teachers have photo+bio."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    # With empty DB, no "Nasi Nauczyciele" section
    assert "Nasi Nauczyciele" not in r.text
```

- [ ] **Step 2: Run to verify it fails**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_landing_page_teacher_section_hidden_when_no_teachers -v
```
Expected: FAILED (section currently not present but test may pass coincidentally — if it already passes, skip to step 3)

- [ ] **Step 3: Update the `/` route handler**

In `app/api/routes_landing.py`, replace the existing `landing_page` handler:

```python
@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the main landing page with featured teachers."""
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .where(User.photo_url.isnot(None))
        .where(User.bio.isnot(None))
        .order_by(User.created_at.asc())
        .limit(3)
    )
    featured_teachers = result.scalars().all()
    return templates.TemplateResponse(
        "landing/index.html",
        {"request": request, "featured_teachers": featured_teachers},
    )
```

- [ ] **Step 4: Add teacher section to `index.html`**

In `app/templates/landing/index.html`, add the following section between the Subjects section closing `</section>` + divider and the "HOW IT WORKS" section. Insert after `<!-- Divider -->` that follows subjects:

```html
<!-- Divider -->
<div class="border-t border-ink/10"></div>

{% if featured_teachers %}
<!-- ─── TEACHERS ──────────────────────────────────────────────────────────── -->
<section id="nauczyciele" class="py-24 px-4 sm:px-6 scroll-mt-16">
    <div class="max-w-7xl mx-auto">
        <div class="mb-14 flex items-end justify-between">
            <div>
                <p class="text-xs font-medium text-ink/40 tracking-[0.2em] uppercase mb-3">Zespół</p>
                <h2 class="font-serif text-4xl md:text-5xl font-bold text-ink">Nasi Nauczyciele</h2>
            </div>
            <a href="/nauczyciele"
               class="text-sm text-navy font-medium hover:underline hidden sm:block">
                Poznaj cały zespół →
            </a>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-10">
            {% for teacher in featured_teachers %}
            <a href="/nauczyciele/{{ teacher.id }}"
               class="border border-ink/10 p-6 hover:border-navy/30 hover:bg-navy/5 transition-colors group block">
                <div class="flex items-center gap-4 mb-4">
                    {% if teacher.photo_url %}
                    <img src="{{ teacher.photo_url }}" alt="{{ teacher.full_name }}"
                         class="w-16 h-16 object-cover flex-shrink-0">
                    {% else %}
                    <div class="w-16 h-16 bg-navy flex items-center justify-center flex-shrink-0">
                        <span class="text-cream font-serif text-xl font-bold">
                            {{ teacher.full_name[:2].upper() }}
                        </span>
                    </div>
                    {% endif %}
                    <div>
                        <p class="font-semibold text-ink group-hover:text-navy transition-colors">{{ teacher.full_name }}</p>
                        {% if teacher.specialties %}
                        <p class="text-xs text-navy/70 mt-0.5">{{ teacher.specialties }}</p>
                        {% endif %}
                    </div>
                </div>
                {% if teacher.bio %}
                <p class="text-sm text-ink/60 leading-relaxed line-clamp-3">
                    {{ teacher.bio[:120] }}{% if teacher.bio|length > 120 %}…{% endif %}
                </p>
                {% endif %}
            </a>
            {% endfor %}
        </div>

        <div class="text-center sm:hidden">
            <a href="/nauczyciele" class="text-sm text-navy font-medium hover:underline">
                Poznaj cały zespół →
            </a>
        </div>
    </div>
</section>

<!-- Divider -->
<div class="border-t border-ink/10"></div>
{% endif %}
```

- [ ] **Step 5: Run test**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py::test_landing_page_teacher_section_hidden_when_no_teachers -v
```
Expected: PASSED (with empty DB, section is hidden)

- [ ] **Step 6: Run all tests to check no regressions**

```bash
docker-compose exec web pytest tests/ -v
```
Expected: all existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add app/api/routes_landing.py app/templates/landing/index.html
git commit -m "feat(landing): add live teacher section to main page, hidden when empty"
```

---

## Task 5: Teacher List + Profile Pages

**Files:**
- Modify: `app/api/routes_landing.py`
- Create: `app/templates/landing/teachers.html`
- Create: `app/templates/landing/teacher_profile.html`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_landing_redesign.py`:

```python
async def test_teachers_list_page_returns_200():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/nauczyciele")
    assert r.status_code == 200
    assert "Nauczyciele" in r.text


async def test_teacher_profile_unknown_id_returns_404():
    from app.main import app
    import uuid
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/nauczyciele/{uuid.uuid4()}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py -k "teachers_list or teacher_profile" -v
```
Expected: both FAILED

- [ ] **Step 3: Add routes to `app/api/routes_landing.py`**

```python
@router.get("/nauczyciele", response_class=HTMLResponse)
async def teachers_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the full teachers list page."""
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .order_by(User.created_at.asc())
    )
    teachers = result.scalars().all()
    return templates.TemplateResponse(
        "landing/teachers.html",
        {"request": request, "teachers": teachers},
    )


@router.get("/nauczyciele/{teacher_id}", response_class=HTMLResponse)
async def teacher_profile_page(
    teacher_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render an individual teacher profile page."""
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return templates.TemplateResponse(
        "landing/teacher_profile.html",
        {"request": request, "teacher": teacher},
    )
```

- [ ] **Step 4: Create `app/templates/landing/teachers.html`**

```html
{% extends "base.html" %}

{% block html_attrs %}{% endblock %}
{% block body_attrs %}class="bg-cream text-ink font-sans antialiased min-h-screen"{% endblock %}
{% block navbar %}{% include "components/navbar_landing.html" %}{% endblock %}
{% block title %}Nasi Nauczyciele — Ekorepetycje{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-4 sm:px-6 max-w-7xl mx-auto">

    <nav class="mb-10 text-xs text-ink/40 tracking-wide">
        <a href="/" class="hover:text-navy transition-colors">Strona główna</a>
        <span class="mx-2">·</span>
        <span class="text-ink/60">Nauczyciele</span>
    </nav>

    <div class="mb-16">
        <p class="text-xs font-medium text-ink/40 tracking-[0.2em] uppercase mb-4">Zespół</p>
        <h1 class="font-serif text-4xl md:text-5xl font-bold text-ink">Nasi Nauczyciele</h1>
    </div>

    {% if teachers %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {% for teacher in teachers %}
        <a href="/nauczyciele/{{ teacher.id }}"
           class="border border-ink/10 p-6 hover:border-navy/30 hover:bg-navy/5 transition-colors group block">
            <div class="flex items-center gap-4 mb-4">
                {% if teacher.photo_url %}
                <img src="{{ teacher.photo_url }}" alt="{{ teacher.full_name }}"
                     class="w-16 h-16 object-cover flex-shrink-0">
                {% else %}
                <div class="w-16 h-16 bg-navy flex items-center justify-center flex-shrink-0">
                    <span class="text-cream font-serif text-xl font-bold">
                        {{ teacher.full_name[:2].upper() }}
                    </span>
                </div>
                {% endif %}
                <div>
                    <p class="font-semibold text-ink group-hover:text-navy transition-colors">{{ teacher.full_name }}</p>
                    {% if teacher.specialties %}
                    <p class="text-xs text-navy/70 mt-0.5">{{ teacher.specialties }}</p>
                    {% endif %}
                </div>
            </div>
            {% if teacher.bio %}
            <p class="text-sm text-ink/60 leading-relaxed">
                {{ teacher.bio[:120] }}{% if teacher.bio|length > 120 %}…{% endif %}
            </p>
            {% else %}
            <p class="text-sm text-ink/30 italic">Brak opisu.</p>
            {% endif %}
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="border border-ink/10 p-16 text-center">
        <p class="text-ink/40">Wkrótce poznasz nasz zespół.</p>
    </div>
    {% endif %}

    <div class="mt-20 border-t border-ink/10 pt-16 text-center">
        <p class="text-ink/60 mb-6">Chcesz dołączyć do zespołu lub umówić się na lekcję?</p>
        <a href="/#kontakt"
           class="inline-flex items-center gap-2 bg-navy hover:bg-navy/90 text-cream font-medium px-8 py-3.5 transition-colors text-sm tracking-wide">
            Skontaktuj się z nami
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 8l4 4m0 0l-4 4m4-4H3"/>
            </svg>
        </a>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create `app/templates/landing/teacher_profile.html`**

```html
{% extends "base.html" %}

{% block html_attrs %}{% endblock %}
{% block body_attrs %}class="bg-cream text-ink font-sans antialiased min-h-screen"{% endblock %}
{% block navbar %}{% include "components/navbar_landing.html" %}{% endblock %}
{% block title %}{{ teacher.full_name }} — Ekorepetycje{% endblock %}

{% block content %}
<div class="pt-24 pb-16 px-4 sm:px-6 max-w-3xl mx-auto">

    <nav class="mb-10 text-xs text-ink/40 tracking-wide">
        <a href="/" class="hover:text-navy transition-colors">Strona główna</a>
        <span class="mx-2">·</span>
        <a href="/nauczyciele" class="hover:text-navy transition-colors">Nauczyciele</a>
        <span class="mx-2">·</span>
        <span class="text-ink/60">{{ teacher.full_name }}</span>
    </nav>

    <div class="flex items-start gap-8 mb-12">
        {% if teacher.photo_url %}
        <img src="{{ teacher.photo_url }}" alt="{{ teacher.full_name }}"
             class="w-32 h-32 object-cover flex-shrink-0">
        {% else %}
        <div class="w-32 h-32 bg-navy flex items-center justify-center flex-shrink-0">
            <span class="text-cream font-serif text-4xl font-bold">
                {{ teacher.full_name[:2].upper() }}
            </span>
        </div>
        {% endif %}
        <div class="pt-2">
            <h1 class="font-serif text-3xl md:text-4xl font-bold text-ink mb-2">{{ teacher.full_name }}</h1>
            {% if teacher.specialties %}
            <div class="flex flex-wrap gap-2">
                {% for s in teacher.specialties.split(',') %}
                <span class="text-xs text-navy border border-navy/30 px-3 py-1 tracking-wide">{{ s.strip() }}</span>
                {% endfor %}
            </div>
            {% endif %}
        </div>
    </div>

    {% if teacher.bio %}
    <div class="prose prose-lg max-w-none text-ink/70 leading-relaxed mb-16">
        <p>{{ teacher.bio }}</p>
    </div>
    {% endif %}

    <div class="border-t border-ink/10 pt-12 text-center">
        <p class="text-ink/60 mb-6">Umów lekcję z {{ teacher.full_name }} — pierwsza konsultacja jest bezpłatna.</p>
        <a href="/#kontakt"
           class="inline-flex items-center gap-2 bg-navy hover:bg-navy/90 text-cream font-medium px-8 py-3.5 transition-colors text-sm tracking-wide">
            Umów bezpłatną konsultację
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 8l4 4m0 0l-4 4m4-4H3"/>
            </svg>
        </a>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Run tests**

```bash
docker-compose exec web pytest tests/test_landing_redesign.py -k "teachers_list or teacher_profile" -v
```
Expected: both PASSED

- [ ] **Step 7: Rebuild Tailwind + commit**

```bash
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css
git add app/api/routes_landing.py app/templates/landing/teachers.html app/templates/landing/teacher_profile.html app/static/css/style.css
git commit -m "feat(landing): add /nauczyciele list and /nauczyciele/{id} profile pages"
```

---

## Task 6: Photo Upload + Profile PATCH API Endpoints

**Files:**
- Modify: `app/api/routes_api.py`
- Create: `tests/test_teacher_profile_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_teacher_profile_api.py`:

```python
"""Tests for teacher photo upload and profile PATCH endpoints."""
import io
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image


def _make_jpeg_bytes() -> bytes:
    """Create a tiny valid JPEG image in memory."""
    img = Image.new("RGB", (10, 10), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def test_upload_photo_unauthenticated_returns_401_or_redirect():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/teachers/me/photo",
            files={"file": ("photo.jpg", _make_jpeg_bytes(), "image/jpeg")},
        )
    # Must not be 200 without auth
    assert r.status_code in (401, 403, 302, 303)


async def test_patch_profile_unauthenticated_returns_401_or_redirect():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            "/api/teachers/me/profile",
            data={"bio": "Test bio", "specialties": "Matematyka"},
        )
    assert r.status_code in (401, 403, 302, 303)


async def test_upload_endpoint_exists_not_404():
    """The upload endpoint must exist (not 404). Auth will fire before MIME check."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/teachers/me/photo",
            files={"file": ("malware.php", b"<?php echo 1; ?>", "image/jpeg")},
        )
    # Auth fires first → 401/403/redirect. Not 404 = endpoint is registered.
    assert r.status_code in (401, 403, 302, 303)
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker-compose exec web pytest tests/test_teacher_profile_api.py -v
```
Expected: FAILED with 404 (endpoints don't exist yet)

- [ ] **Step 3: Add endpoints to `app/api/routes_api.py`**

Add imports at the top of `routes_api.py` (after existing imports):
```python
import io
from pathlib import Path
from fastapi import UploadFile, File
from fastapi.responses import HTMLResponse
from PIL import Image, UnidentifiedImageError
```
Note: `require_teacher_or_admin` is already imported in `routes_api.py` (line 12: `from app.core.auth import get_current_user, require_teacher_or_admin`). No new import needed for this dependency.

Add these four endpoints at the end of `routes_api.py`:

```python
# ─── Teacher profile: photo upload ────────────────────────────────────────────

_PHOTO_DIR = Path("app/static/img/teachers")
_MAX_PHOTO_BYTES = 2_000_000


@router.post("/teachers/me/photo", response_class=HTMLResponse)
async def upload_own_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Teacher uploads their own profile photo. Returns an HTML <img> fragment."""
    return await _save_teacher_photo(file, current_user, db)


@router.post("/admin/teachers/{teacher_id}/photo", response_class=HTMLResponse)
async def admin_upload_teacher_photo(
    teacher_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Admin uploads a photo for any teacher."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return await _save_teacher_photo(file, teacher, db)


async def _save_teacher_photo(
    file: UploadFile,
    teacher: User,
    db: AsyncSession,
) -> HTMLResponse:
    """Shared logic: validate, convert, save, update DB, return HTML fragment."""
    if file.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=422, detail="Only JPEG or PNG images are accepted")
    data = await file.read()
    if len(data) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=422, detail="Image must be under 2 MB")
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(status_code=422, detail="Invalid image file")
    _PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    dest = _PHOTO_DIR / f"{teacher.id}.jpg"
    img.save(dest, format="JPEG", quality=85)
    photo_url = f"/static/img/teachers/{teacher.id}.jpg"
    teacher.photo_url = photo_url
    await db.flush()
    return HTMLResponse(
        f'<img id="teacher-photo" src="{photo_url}?v={teacher.id}" '
        f'alt="{teacher.full_name}" class="w-20 h-20 object-cover">'
    )


# ─── Teacher profile: bio + specialties ───────────────────────────────────────

@router.patch("/teachers/me/profile")
async def update_own_profile(
    bio: str = Form(default=""),
    specialties: str = Form(default=""),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Teacher updates their own bio and specialties."""
    current_user.bio = bio.strip() or None
    current_user.specialties = specialties.strip() or None
    await db.flush()
    return {"ok": True}


@router.patch("/admin/teachers/{teacher_id}/profile")
async def admin_update_teacher_profile(
    teacher_id: UUID,
    bio: str = Form(default=""),
    specialties: str = Form(default=""),
    current_user: User = Depends(require_teacher_or_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin updates bio and specialties for any teacher."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(status_code=404, detail="Teacher not found")
    teacher.bio = bio.strip() or None
    teacher.specialties = specialties.strip() or None
    await db.flush()
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

```bash
docker-compose exec web pytest tests/test_teacher_profile_api.py -v
```
Expected: all PASSED (endpoints exist now, auth guard fires correctly)

- [ ] **Step 5: Run all tests**

```bash
docker-compose exec web pytest tests/ -v
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/api/routes_api.py tests/test_teacher_profile_api.py
git commit -m "feat(api): add teacher photo upload and profile PATCH endpoints"
```

---

## Task 7: Teacher Dashboard — Profile Edit Card

**Files:**
- Modify: `app/templates/teacher/dashboard.html`

- [ ] **Step 1: Add profile edit card to dashboard**

In `app/templates/teacher/dashboard.html`, add the following section **before** the closing `</div>` of the main container (after the events list block, before the closing `</div>` of `max-w-5xl mx-auto`):

```html
<!-- Profile edit card -->
<div class="mt-8 bg-gray-900/50 border border-gray-800/50 rounded-2xl p-6">
    <h2 class="text-lg font-semibold text-white mb-6">Mój profil publiczny</h2>
    <div class="flex flex-col sm:flex-row gap-8">

        <!-- Photo column -->
        <div class="flex flex-col items-center gap-3 sm:w-32">
            {% if user.photo_url %}
            <img id="teacher-photo" src="{{ user.photo_url }}" alt="{{ user.full_name }}"
                 class="w-20 h-20 object-cover">
            {% else %}
            <div id="teacher-photo"
                 class="w-20 h-20 bg-gray-700 flex items-center justify-center text-gray-300 font-semibold text-xl">
                {{ user.full_name[:2].upper() }}
            </div>
            {% endif %}
            <form enctype="multipart/form-data"
                  hx-post="/api/teachers/me/photo"
                  hx-target="#teacher-photo"
                  hx-swap="outerHTML">
                <label class="cursor-pointer text-xs text-gray-400 hover:text-white transition-colors">
                    Zmień zdjęcie
                    <input type="file" name="file" accept="image/jpeg,image/png"
                           class="hidden" onchange="this.form.requestSubmit()">
                </label>
            </form>
        </div>

        <!-- Bio + specialties column -->
        <form class="flex-1 space-y-4"
              hx-patch="/api/teachers/me/profile"
              hx-swap="none"
              hx-on::after-request="document.getElementById('profile-saved').classList.remove('hidden');setTimeout(()=>document.getElementById('profile-saved').classList.add('hidden'),2000)">
            <div>
                <label class="block text-xs text-gray-400 mb-1 uppercase tracking-wide">Bio</label>
                <textarea name="bio" maxlength="500" rows="4"
                          class="w-full bg-gray-800 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-green-500 resize-none"
                          placeholder="Kilka słów o sobie, doświadczeniu, metodzie pracy...">{{ user.bio or '' }}</textarea>
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1 uppercase tracking-wide">Przedmioty (oddzielone przecinkiem)</label>
                <input type="text" name="specialties"
                       value="{{ user.specialties or '' }}"
                       placeholder="np. Matematyka,Fizyka"
                       class="w-full bg-gray-800 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-green-500">
                <p class="text-xs text-gray-500 mt-1">Używaj dokładnie: Matematyka, Fizyka, Informatyka, Języki</p>
            </div>
            <div class="flex items-center gap-3">
                <button type="submit"
                        class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-4 py-2 rounded-lg text-sm transition-colors">
                    Zapisz
                </button>
                <span id="profile-saved" class="hidden text-xs text-green-400">Zapisano ✓</span>
            </div>
        </form>
    </div>
</div>
```

- [ ] **Step 2: Quick smoke test**

```bash
docker-compose exec web pytest tests/ -v
```
Expected: all pass (no regression)

- [ ] **Step 3: Visual verification**

Login as a teacher at `http://localhost:8000/login` and visit `/teacher/`. Verify the "Mój profil publiczny" card appears with bio textarea and specialties input. Try uploading a photo.

- [ ] **Step 4: Commit**

```bash
git add app/templates/teacher/dashboard.html
git commit -m "feat(teacher): add profile edit card to teacher dashboard"
```

---

## Task 8: Admin — Teacher Profile Management

**Files:**
- Modify: `app/templates/admin/users.html`

- [ ] **Step 1: Add profile edit button + expandable form per teacher row**

In `app/templates/admin/users.html`, in the actions `<td>` (line ~80), add an "Edytuj profil" button after the existing role/password forms for teacher-role users:

Find the `<td class="px-6 py-4">` actions cell and add inside the `<div class="flex items-center gap-3">`:

```html
{% if user.role.value == 'teacher' %}
<!-- Teacher profile edit expand -->
<button onclick="document.getElementById('profile-{{ user.id }}').classList.toggle('hidden')"
        class="text-xs text-gray-400 hover:text-green-400 transition-colors">
    Edytuj profil
</button>
{% endif %}
```

Then add a collapsible row after the `</tr>` closing tag of each user:

```html
{% if user.role.value == 'teacher' %}
<tr id="profile-{{ user.id }}" class="hidden bg-gray-800/20">
    <td colspan="4" class="px-6 py-4">
        <div class="flex flex-col sm:flex-row gap-6">
            <!-- Photo upload -->
            <div class="flex flex-col items-start gap-2 sm:w-48">
                {% if user.photo_url %}
                <img id="admin-photo-{{ user.id }}" src="{{ user.photo_url }}"
                     alt="{{ user.full_name }}" class="w-16 h-16 object-cover">
                {% else %}
                <div id="admin-photo-{{ user.id }}"
                     class="w-16 h-16 bg-gray-700 flex items-center justify-center text-white font-semibold">
                    {{ user.full_name[:2].upper() }}
                </div>
                {% endif %}
                <form enctype="multipart/form-data"
                      hx-post="/api/admin/teachers/{{ user.id }}/photo"
                      hx-target="#admin-photo-{{ user.id }}"
                      hx-swap="outerHTML">
                    <label class="cursor-pointer text-xs text-gray-400 hover:text-white">
                        Zmień zdjęcie
                        <input type="file" name="file" accept="image/jpeg,image/png"
                               class="hidden" onchange="this.form.requestSubmit()">
                    </label>
                </form>
            </div>
            <!-- Bio + specialties -->
            <form class="flex-1 space-y-3"
                  hx-patch="/api/admin/teachers/{{ user.id }}/profile"
                  hx-swap="none"
                  hx-on::after-request="document.getElementById('admin-saved-{{ user.id }}').classList.remove('hidden');setTimeout(()=>document.getElementById('admin-saved-{{ user.id }}').classList.add('hidden'),2000)">
                <div>
                    <label class="block text-xs text-gray-400 mb-1 uppercase tracking-wide">Bio</label>
                    <textarea name="bio" rows="3" maxlength="500"
                              class="w-full bg-gray-800 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-green-500 resize-none"
                              >{{ user.bio or '' }}</textarea>
                </div>
                <div>
                    <label class="block text-xs text-gray-400 mb-1 uppercase tracking-wide">Przedmioty</label>
                    <input type="text" name="specialties"
                           value="{{ user.specialties or '' }}"
                           placeholder="np. Matematyka,Fizyka"
                           class="w-full bg-gray-800 border border-gray-700 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:border-green-500">
                </div>
                <div class="flex items-center gap-3">
                    <button type="submit"
                            class="bg-green-500 hover:bg-green-400 text-gray-950 font-semibold px-4 py-2 rounded-lg text-sm transition-colors">
                        Zapisz
                    </button>
                    <span id="admin-saved-{{ user.id }}" class="hidden text-xs text-green-400">Zapisano ✓</span>
                </div>
            </form>
        </div>
    </td>
</tr>
{% endif %}
```

- [ ] **Step 2: Run all tests**

```bash
docker-compose exec web pytest tests/ -v
```
Expected: all pass

- [ ] **Step 3: Visual verification**

Login as admin at `http://localhost:8000/login`, go to `/admin/users`. Click "Edytuj profil" on a teacher row to verify the expand works. Fill in bio + specialties and save, then reload and check values persist.

- [ ] **Step 4: Commit**

```bash
git add app/templates/admin/users.html
git commit -m "feat(admin): add teacher profile edit expand in users table"
```

---

## Task 9: Tailwind Rebuild + Full Regression + Push

- [ ] **Step 1: Final Tailwind rebuild**

```bash
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css
```

- [ ] **Step 2: Run full test suite**

```bash
docker-compose exec web pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 3: Full visual walkthrough**
Check all these URLs work and look correct:
- `http://localhost:8000/` — hero centered, subject cards renamed, no filter tabs, "Dowiedz się więcej" links, teacher section hidden (or shown if teachers have bio+photo in seed)
- `http://localhost:8000/przedmioty/matematyka` — static content + empty teacher grid
- `http://localhost:8000/przedmioty/informatyka` — static content
- `http://localhost:8000/przedmioty/jezyki-obce` — static content
- `http://localhost:8000/nauczyciele` — teacher list (empty state shown)
- `http://localhost:8000/nauczyciele/<some-id>` — 404 for random UUID ✓
- `http://localhost:8000/teacher/` (as teacher) — profile edit card visible
- `http://localhost:8000/admin/users` (as admin) — "Edytuj profil" on teacher rows

- [ ] **Step 4: Final commit + push**

```bash
git add app/static/css/style.css
git commit -m "chore: rebuild Tailwind CSS for landing redesign"
git push origin main
```

---

## Testing Commands Reference

```bash
# Run all tests
docker-compose exec web pytest tests/ -v

# Run only new tests
docker-compose exec web pytest tests/test_landing_redesign.py tests/test_teacher_profile_api.py -v

# Run with coverage
docker-compose exec web pytest tests/ --tb=short

# Rebuild Tailwind
npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css

# Run migration
docker-compose exec web alembic upgrade head

# Seed DB (if needed)
docker-compose exec web bash -c "cd /app && python -m scripts.seed"
```
