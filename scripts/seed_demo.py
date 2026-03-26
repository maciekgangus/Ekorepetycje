"""Demo seed script — inserts realistic tutoring platform data."""
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.series import RecurringSeries
from app.models.availability import UnavailableBlock
from app.models.unavail_series import RecurringUnavailSeries
from app.models.proposals import RescheduleProposal

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@db:5432/ekorepetycje",
)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ── Data ─────────────────────────────────────────────────────────────────────

TEACHERS = [
    {"full_name": "Anna Kowalska",    "email": "anna@eko.pl",    "specialties": "Matematyka, Fizyka"},
    {"full_name": "Piotr Nowak",      "email": "piotr@eko.pl",   "specialties": "Język angielski, Niemiecki"},
    {"full_name": "Marta Wiśniewska", "email": "marta@eko.pl",   "specialties": "Biologia, Chemia"},
    {"full_name": "Tomasz Zając",     "email": "tomasz@eko.pl",  "specialties": "Historia, WOS"},
    {"full_name": "Karolina Dąbek",   "email": "karolina@eko.pl","specialties": "Matematyka, Informatyka"},
]

STUDENTS = [
    "Marek Adamski", "Julia Brzezińska", "Krzysztof Chmura", "Zofia Duda",
    "Bartosz Elas", "Natalia Fila", "Grzegorz Gajda", "Aleksandra Hajduk",
    "Michał Igielski", "Weronika Janik", "Paweł Kaczmarek", "Monika Lewandowska",
    "Rafał Malinowski", "Ewa Nowacka", "Szymon Okoń",
]

OFFERINGS_BY_TEACHER = [
    # Anna — math / physics
    [
        ("Matematyka — Matura Rozszerzona", "Intensywne przygotowanie do matury rozszerzonej.", 90),
        ("Fizyka — Matura Podstawowa",      "Wzory, zadania, testy próbne.",                    80),
    ],
    # Piotr — languages
    [
        ("Angielski B2–C1",    "Konwersacje i przygotowanie do Cambridge FCE/CAE.",          70),
        ("Język Niemiecki A2", "Gramatyka i słownictwo od podstaw.",                         65),
    ],
    # Marta — bio / chem
    [
        ("Biologia — Matura Rozszerzona", "Genetyka, ekologia, anatomia — pełen zakres.",    85),
        ("Chemia Organiczna",              "Reakcje, mechanizmy, zadania rachunkowe.",         80),
    ],
    # Tomasz — humanities
    [
        ("Historia — Matura",  "Daty, mapy, analiza źródeł historycznych.",                  60),
        ("WOS — Matura",       "Ustrój, prawo, społeczeństwo obywatelskie.",                  55),
    ],
    # Karolina — math / IT
    [
        ("Matematyka — Klasy 7–8",  "Zadania z egzaminu ósmoklasisty.",                       75),
        ("Programowanie Python",    "Podstawy algorytmiki i przygotowanie do olimpiady.",     100),
    ],
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def rand_slot(base: datetime, teacher_idx: int) -> tuple[datetime, datetime]:
    """Return a random (start, end) 1-or-1.5h slot anchored to base day."""
    hour = random.choice([9, 10, 11, 13, 14, 15, 16, 17, 18, 19])
    duration = random.choice([60, 90])
    start = base.replace(hour=hour, minute=0, second=0, microsecond=0)
    return start, start + timedelta(minutes=duration)


# ── Main ──────────────────────────────────────────────────────────────────────

async def seed():
    async with AsyncSessionLocal() as db:
        # ── 0. Wipe existing non-admin data (in FK order) ────────────────────
        await db.execute(delete(RescheduleProposal))
        await db.execute(delete(UnavailableBlock))
        await db.execute(delete(RecurringUnavailSeries))
        await db.execute(delete(ScheduleEvent))
        await db.execute(delete(RecurringSeries))
        await db.execute(delete(Offering))

        existing = await db.execute(select(User).where(User.role != UserRole.ADMIN))
        for u in existing.scalars().all():
            await db.delete(u)
        await db.flush()

        # ── 0b. Ensure default admin exists ──────────────────────────────────
        admin_row = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        if admin_row.scalar_one_or_none() is None:
            hp_admin = pwd_ctx.hash("admin123")
            db.add(User(
                id=uuid.uuid4(), role=UserRole.ADMIN,
                email="admin@eko.pl", hashed_password=hp_admin,
                full_name="Admin Główny",
            ))
            await db.flush()
            print("✓ Created default admin: admin@eko.pl / admin123")

        # ── 1. Create teachers ────────────────────────────────────────────────
        hp = pwd_ctx.hash("haslo123")
        teacher_objs: list[User] = []
        for t in TEACHERS:
            u = User(
                id=uuid.uuid4(), role=UserRole.TEACHER,
                email=t["email"], hashed_password=hp,
                full_name=t["full_name"], specialties=t["specialties"],
                bio=f"Doświadczony korepetytor — {t['specialties']}.",
            )
            db.add(u)
            teacher_objs.append(u)

        # ── 2. Create students ────────────────────────────────────────────────
        student_objs: list[User] = []
        for name in STUDENTS:
            first = name.split()[0].lower()
            u = User(
                id=uuid.uuid4(), role=UserRole.STUDENT,
                email=f"{first}@student.pl", hashed_password=hp,
                full_name=name,
            )
            db.add(u)
            student_objs.append(u)

        await db.flush()

        # ── 3. Create offerings ────────────────────────────────────────────────
        offering_objs: list[list[Offering]] = []
        for i, teacher in enumerate(teacher_objs):
            teacher_offerings: list[Offering] = []
            for title, desc, price in OFFERINGS_BY_TEACHER[i]:
                o = Offering(
                    id=uuid.uuid4(), title=title, description=desc,
                    base_price_per_hour=price, teacher_id=teacher.id,
                )
                db.add(o)
                teacher_offerings.append(o)
            offering_objs.append(teacher_offerings)

        await db.flush()

        # ── 4. Generate events across last 6 months + next 4 weeks ────────────
        today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)

        events: list[ScheduleEvent] = []

        # Past events: spread ~200 completed + ~25 cancelled over 6 months
        for day_offset in range(-180, 0):
            day = today + timedelta(days=day_offset)
            if day.weekday() == 6:  # skip Sundays
                continue
            # Each teacher has ~40% chance of having a lesson on any given day
            for t_idx, teacher in enumerate(teacher_objs):
                if random.random() > 0.40:
                    continue
                offering = random.choice(offering_objs[t_idx])
                student = random.choice(student_objs)
                start, end = rand_slot(day, t_idx)

                status = EventStatus.CANCELLED if random.random() < 0.10 else EventStatus.COMPLETED

                events.append(ScheduleEvent(
                    id=uuid.uuid4(),
                    title=offering.title,
                    start_time=start, end_time=end,
                    offering_id=offering.id,
                    teacher_id=teacher.id,
                    student_id=student.id,
                    status=status,
                ))

        # Future events: next 4 weeks, all SCHEDULED
        for day_offset in range(1, 29):
            day = today + timedelta(days=day_offset)
            if day.weekday() >= 6:
                continue
            for t_idx, teacher in enumerate(teacher_objs):
                if random.random() > 0.50:
                    continue
                offering = random.choice(offering_objs[t_idx])
                student = random.choice(student_objs)
                start, end = rand_slot(day, t_idx)
                events.append(ScheduleEvent(
                    id=uuid.uuid4(),
                    title=offering.title,
                    start_time=start, end_time=end,
                    offering_id=offering.id,
                    teacher_id=teacher.id,
                    student_id=student.id,
                    status=EventStatus.SCHEDULED,
                ))

        for ev in events:
            db.add(ev)

        await db.commit()

        total = len(events)
        completed = sum(1 for e in events if e.status == EventStatus.COMPLETED)
        scheduled = sum(1 for e in events if e.status == EventStatus.SCHEDULED)
        cancelled = sum(1 for e in events if e.status == EventStatus.CANCELLED)
        print(f"✓ {len(teacher_objs)} teachers, {len(student_objs)} students, {len(sum(offering_objs,[]))} offerings")
        print(f"✓ {total} events — {completed} completed / {scheduled} scheduled / {cancelled} cancelled")
        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
