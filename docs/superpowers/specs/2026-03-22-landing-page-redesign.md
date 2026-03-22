# Landing Page Redesign — Design Spec
**Date:** 2026-03-22
**Status:** Approved

## Overview

Refactor the Ekorepetycje landing page to fix the full-width layout, simplify subject naming, add subject detail pages, add a live teacher section, and wire teacher profiles (photo + bio) to the admin panel. All changes must be mobile-first.

---

## 1. Hero Section — Layout Fix

**Problem:** The hero `<section>` has no max-width, so content spreads edge-to-edge on wide monitors causing the left column to appear misaligned.

**Fix:** Wrap the inner `grid` in a `div` with `max-w-7xl mx-auto w-full`. The five-column `lg:grid-cols-5` grid structure stays on the inner div. The outer `<section>` keeps `px-6` for edge padding.

**Mobile behavior:** On `< lg` breakpoints the grid collapses to single-column: headline first, stat cards + testimonial below, both full-width.

**No changes to** color, fonts, CTA buttons, or hero copy. The `&amp;` in the hero subheading (`Warszawa &amp; Online`) stays as-is — the ampersand fix (Section 2) applies only to subject names.

---

## 2. Typography — Remove Ornate Ampersand

**Problem:** Playfair Display renders `&` as a decorative glyph that looks out of place in subject names.

**Fix:** Replace `&amp;` only in subject card headings with the Polish conjunction `i`:
- `Matematyka &amp; Fizyka` → `Matematyka i Fizyka`
- `Programowanie &amp; IT` → `Informatyka i IT`

No font change. Scope is subject cards in `index.html` and any new subject-related templates only.

---

## 3. Subjects Section — Simplification

**Filter tabs removed:** The HTMX filter tabs (Podstawówka / Liceum / Studia) and the associated `hx-get="/subjects?level=..."` markup are deleted entirely. No backend `/subjects` endpoint needs to be created. Level badges remain inside each card as decorative tags.

**Cards renamed:**
| Old | New |
|-----|-----|
| Matematyka & Fizyka | Matematyka i Fizyka |
| Programowanie & IT | Informatyka i IT |
| Języki Obce | Języki Obce (unchanged) |

**"Dowiedz się więcej →" link** added at the bottom of each card (replacing or after the level badges), linking to:
- `/przedmioty/matematyka`
- `/przedmioty/informatyka`
- `/przedmioty/jezyki-obce`

**Grid:** stays `md:grid-cols-3 gap-px bg-ink/10`, mobile stacks to 1-col (no intermediate 2-col at tablet for this section — goes straight from 1-col to 3-col at `md`).

---

## 4. Subject Detail Pages

Three new routes in `routes_landing.py` (HTML responses only, per routing rules):
- `GET /przedmioty/matematyka`
- `GET /przedmioty/informatyka`
- `GET /przedmioty/jezyki-obce`

Single shared template: `landing/subject_detail.html`, rendered with a `subject` string context variable.

**Specialties keyword map** (used to filter teachers — case-insensitive `ILIKE` on the `specialties` column):

| Route slug | Keyword |
|------------|---------|
| `matematyka` | `Matematyka` |
| `informatyka` | `Informatyka` |
| `jezyki-obce` | `Języki` |

**`routes_landing.py` requires these new imports at the top:**
```python
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models.users import User, UserRole
```

**`specialties` canonical format:** values stored in the DB must exactly match one of the keyword map entries or be comma-separated combinations thereof (e.g. `"Matematyka,Fizyka"`). No extra words or spaces around commas. The ILIKE `%keyword%` will then match correctly and not produce false positives.

**Route handler example (in `routes_landing.py`):**
```python
@router.get("/przedmioty/{slug}")
async def subject_detail(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    keyword_map = {
        "matematyka": "Matematyka",
        "informatyka": "Informatyka",
        "jezyki-obce": "Języki",
    }
    if slug not in keyword_map:
        raise HTTPException(404)
    keyword = keyword_map[slug]
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.TEACHER)
        .where(User.specialties.ilike(f"%{keyword}%"))
        .order_by(User.created_at.asc())
    )
    teachers = result.scalars().all()
    return templates.TemplateResponse("landing/subject_detail.html", {
        "request": request, "subject": slug, "teachers": teachers,
    })
```

**Page structure:**
1. Shared landing navbar
2. Static description block — heading + 3–4 paragraphs, selected via `{% if subject == "matematyka" %}` blocks in the template
3. Dynamic teacher grid — `{% if teachers %}` guard; heading "Nauczyciele tego przedmiotu"; same bio card style as main page teacher section (Section 5)
4. CTA strip — "Umów bezpłatną konsultację" → `/#kontakt`

---

## 5. Teacher Section — Main Page

New section inserted **between Subjects and How It Works** in `index.html`.

**DB query** (in the `/` route handler, `routes_landing.py`):
```python
result = await db.execute(
    select(User)
    .where(User.role == UserRole.TEACHER)
    .where(User.photo_url.isnot(None))
    .where(User.bio.isnot(None))
    .order_by(User.created_at.asc())
    .limit(3)
)
featured_teachers = result.scalars().all()
```
Pass `featured_teachers` to the template context.

**Heading:** "Nasi Nauczyciele"

**Card anatomy (Tailwind class names):**
- Photo: `w-24 h-24 object-cover` square, or initials fallback `w-24 h-24 bg-navy flex items-center justify-center text-cream font-serif text-2xl`
- Full name: bold, `font-semibold text-ink`
- Specialties: `text-xs text-navy tracking-wide` (comma-separated from `user.specialties`)
- Bio excerpt: first 120 chars + `…`, `text-sm text-ink/60 leading-relaxed`
- "Zobacz profil →" link to `/nauczyciele/{teacher.id}`

**Footer link:** "Poznaj cały zespół →" → `/nauczyciele`

**Hidden when:** `{% if featured_teachers %}` — entire section absent when no qualifying teachers.

**Mobile:** Single-column (1-col), tablet 2-col (`sm:grid-cols-2`), desktop 3-col (`lg:grid-cols-3`).

---

## 6. Teacher List Page — `/nauczyciele`

New route `GET /nauczyciele` in `routes_landing.py` → renders `landing/teachers.html`.

Fetches **all** teachers (`role == TEACHER`), ordered by `created_at ASC`, regardless of whether they have a photo or bio (intentional — the list page is exhaustive, the main-page section is curated). Same bio card style; initials fallback for those without a photo.

**Grid:** `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6`

Each card links to `/nauczyciele/{teacher.id}`.

---

## 7. Teacher Profile Page — `/nauczyciele/{teacher_id}`

New route `GET /nauczyciele/{teacher_id}` in `routes_landing.py` → renders `landing/teacher_profile.html`.

**Handler:**
```python
@router.get("/nauczyciele/{teacher_id}")
async def teacher_profile(
    teacher_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    teacher = await db.get(User, teacher_id)
    if not teacher or teacher.role != UserRole.TEACHER:
        raise HTTPException(404)
    return templates.TemplateResponse("landing/teacher_profile.html", {
        "request": request, "teacher": teacher,
    })
```

**Page structure:**
1. Shared landing navbar
2. Teacher card (large photo or initials, full name, specialties)
3. Full bio text (no truncation)
4. CTA: "Umów lekcję z {teacher.full_name}" → `/#kontakt`

---

## 8. Data Model — User

Add four nullable columns to the `users` table:

```python
photo_url:    Mapped[str | None] = mapped_column(String(512), nullable=True)
bio:          Mapped[str | None] = mapped_column(Text, nullable=True)
specialties:  Mapped[str | None] = mapped_column(String(256), nullable=True)
# comma-separated, e.g. "Matematyka,Fizyka" — used for ILIKE filtering
created_at:   Mapped[datetime] = mapped_column(
                  DateTime(timezone=True),
                  server_default=func.now(),
                  nullable=False,
              )
```

**Migration:** single `alembic revision --autogenerate -m "add teacher profile fields and created_at"`.
- `photo_url`, `bio`, `specialties`: ADD COLUMN nullable, no backfill.
- `created_at`: ADD COLUMN with `server_default=now()`, then `ALTER COLUMN SET NOT NULL` — same backfill pattern used in previous migrations.

---

## 9. Photo Upload

**Add `Pillow` to `requirements.txt`** (used for image conversion to JPEG).

**Endpoints (in `routes_api.py`):**
- `POST /api/teachers/me/photo` — authenticated teacher uploads their own photo
- `POST /api/admin/teachers/{teacher_id}/photo` — admin uploads for any teacher

Both use existing cookie-based session auth (`Depends(get_current_user)`). The teacher endpoint guards `current_user.role == TEACHER`. The admin endpoint guards `current_user.role == ADMIN`.

**Handling:**
- Accept `UploadFile` (multipart)
- Validate MIME type: `image/jpeg` or `image/png` only; raise `422` with a clear message if neither
- Validate size: read all bytes into memory (`await file.read()`), reject if `len(data) > 2_000_000`
- Open with Pillow: `Image.open(io.BytesIO(data))` — if Pillow raises `UnidentifiedImageError`, return `422` ("Invalid image file"). This is the true safety net against spoofed MIME types.
- Convert and save: `.convert("RGB").save(dest_path, format="JPEG", quality=85)`
- Directory creation: `Path("app/static/img/teachers").mkdir(parents=True, exist_ok=True)` before every save (idempotent)
- Save to `app/static/img/teachers/{user_id}.jpg` — always overwrites previous upload (no delete step needed)
- Update `user.photo_url = f"/static/img/teachers/{user_id}.jpg"` and `await db.flush()` (session middleware handles commit per request — do not call `await db.commit()` explicitly)
- Return an **HTML fragment** (not JSON) so HTMX `hx-swap="outerHTML"` can replace the `<img>` on the dashboard directly:
  ```python
  return HTMLResponse(f'<img id="teacher-photo" src="{photo_url}" class="w-20 h-20 object-cover">')
  ```

**Bio / specialties update endpoints:**
- `PATCH /api/teachers/me/profile` — accepts `Form(bio=..., specialties=...)` (HTMX sends `application/x-www-form-urlencoded`)
- `PATCH /api/admin/teachers/{teacher_id}/profile` — same form fields, admin auth

Note: HTMX sends `application/x-www-form-urlencoded` by default; endpoints use `bio: str = Form(...)` / `specialties: str = Form(...)` parameters, not Pydantic JSON models. No new schema file needed.

---

## 10. Teacher Dashboard — Profile Edit

Add a "Mój profil" card to the existing teacher dashboard (`/teacher/`):

- Current photo (`<img src="{{user.photo_url}}">`) or initials fallback — `w-20 h-20`
- **Photo form:** `<form enctype="multipart/form-data" hx-post="/api/teachers/me/photo" hx-target="#teacher-photo" hx-swap="outerHTML">` — on success swaps the `<img>` element with fresh URL returned in response fragment
- **Profile form:** `<form hx-patch="/api/teachers/me/profile" hx-swap="none">` with bio textarea (`maxlength="500"`) and specialties text input
- Save button shows a brief "Zapisano ✓" inline confirmation via HTMX

---

## 11. Admin — Teacher Profile Management

On `admin/users.html`, add an "Edytuj profil" button per teacher row. Opens an inline expand (not a modal) showing:
- Photo upload form posting to `/api/admin/teachers/{id}/photo`
- Bio textarea + specialties input posting to `/api/admin/teachers/{id}/profile`

Uses HTMX `hx-get` to load the form fragment lazily on first click.

---

## 12. Mobile Responsiveness

All sections use `max-w-7xl mx-auto px-4 sm:px-6` padding pattern.

| Section | Mobile | Tablet (`sm`/`md`) | Desktop (`lg`) |
|---------|--------|--------|---------|
| Hero | 1-col | 1-col | 5-col grid (`lg:grid-cols-5`) |
| Subjects | 1-col | 3-col (`md:grid-cols-3`) | 3-col |
| Teachers (main) | 1-col | 2-col (`sm:grid-cols-2`) | 3-col (`lg:grid-cols-3`) |
| Teachers list | 1-col | 2-col (`sm:grid-cols-2`) | 3-col (`lg:grid-cols-3`) |
| Subject detail teachers | 1-col | 2-col (`sm:grid-cols-2`) | 3-col (`lg:grid-cols-3`) |

Tap targets ≥ 44px. No horizontal overflow anywhere.

After adding new templates, run Tailwind rebuild: `npx tailwindcss -i ./app/static/css/input.css -o ./app/static/css/style.css`.

---

## 13. Image Storage — Production Note

Dev: local filesystem at `app/static/img/teachers/`. Production: swap write path + `photo_url` prefix to S3 (`https://bucket.s3.amazonaws.com/teachers/{user_id}.jpg`). The `photo_url` DB column stores the full URL in production. Change is isolated to the upload endpoints — templates, API responses, and all other code are unaffected.

---

## Files Affected

| File | Change |
|------|--------|
| `requirements.txt` | Add `Pillow` |
| `app/models/users.py` | Add `photo_url`, `bio`, `specialties`, `created_at` |
| `alembic/versions/...` | New migration (4 columns) |
| `app/api/routes_landing.py` | Fix `/` handler; add `/przedmioty/{slug}`, `/nauczyciele`, `/nauczyciele/{id}` |
| `app/api/routes_api.py` | Add photo upload + profile PATCH endpoints |
| `app/templates/landing/index.html` | Hero max-width fix; subjects rename + remove tabs; add teacher section |
| `app/templates/landing/subject_detail.html` | New |
| `app/templates/landing/teachers.html` | New |
| `app/templates/landing/teacher_profile.html` | New |
| `app/templates/teacher/dashboard.html` | Add profile edit card |
| `app/templates/admin/users.html` | Add "Edytuj profil" per teacher row |
| `app/static/img/teachers/` | New directory (created at runtime) |
| `app/static/css/style.css` | Rebuild after new templates added |
