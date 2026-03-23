"""Seed the database with demo data for development and testing."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent, EventStatus
from app.models.availability import UnavailableBlock

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

NOW = datetime.now(timezone.utc)


async def seed():
    async with AsyncSessionLocal() as db:
        # --- Users ---
        admin = User(
            id=uuid.uuid4(), role=UserRole.ADMIN,
            email="admin@ekorepetycje.pl", full_name="Admin Główny",
            hashed_password=hash_password("admin123"),
        )
        teacher1 = User(
            id=uuid.uuid4(), role=UserRole.TEACHER,
            email="anna@ekorepetycje.pl", full_name="Anna Kowalska",
            hashed_password=hash_password("teacher123"),
        )
        teacher2 = User(
            id=uuid.uuid4(), role=UserRole.TEACHER,
            email="marek@ekorepetycje.pl", full_name="Marek Nowak",
            hashed_password=hash_password("teacher123"),
        )
        student1 = User(
            id=uuid.uuid4(), role=UserRole.STUDENT,
            email="student1@example.com", full_name="Piotr Wiśniewski",
            hashed_password=hash_password("student123"),
        )
        student2 = User(
            id=uuid.uuid4(), role=UserRole.STUDENT,
            email="student2@example.com", full_name="Karolina Dąbrowska",
            hashed_password=hash_password("student123"),
        )
        db.add_all([admin, teacher1, teacher2, student1, student2])
        await db.flush()

        # --- Offerings ---
        off1 = Offering(
            id=uuid.uuid4(), title="Matematyka — Matura Rozszerzona",
            description="Intensywne przygotowanie do matury rozszerzonej.",
            base_price_per_hour=80, teacher_id=teacher1.id,
        )
        off2 = Offering(
            id=uuid.uuid4(), title="Angielski B2–C1",
            description="Konwersacje i przygotowanie do Cambridge FCE/CAE.",
            base_price_per_hour=70, teacher_id=teacher2.id,
        )
        db.add_all([off1, off2])
        await db.flush()

        # --- Schedule Events ---
        events = [
            ScheduleEvent(
                id=uuid.uuid4(), title="Matematyka — Piotr W.",
                start_time=NOW + timedelta(days=1, hours=10),
                end_time=NOW + timedelta(days=1, hours=11),
                offering_id=off1.id, teacher_id=teacher1.id, student_id=student1.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Matematyka — Karolina D.",
                start_time=NOW + timedelta(days=2, hours=14),
                end_time=NOW + timedelta(days=2, hours=15),
                offering_id=off1.id, teacher_id=teacher1.id, student_id=student2.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Angielski — Piotr W.",
                start_time=NOW + timedelta(days=3, hours=9),
                end_time=NOW + timedelta(days=3, hours=10),
                offering_id=off2.id, teacher_id=teacher2.id, student_id=student1.id,
                status=EventStatus.SCHEDULED,
            ),
            ScheduleEvent(
                id=uuid.uuid4(), title="Angielski — Karolina D.",
                start_time=NOW - timedelta(days=5, hours=10),
                end_time=NOW - timedelta(days=5, hours=11),
                offering_id=off2.id, teacher_id=teacher2.id, student_id=student2.id,
                status=EventStatus.COMPLETED,
            ),
        ]
        db.add_all(events)
        await db.flush()

        # --- Unavailable blocks ---
        db.add(UnavailableBlock(
            id=uuid.uuid4(), user_id=teacher1.id,
            start_time=NOW + timedelta(days=4, hours=8),
            end_time=NOW + timedelta(days=4, hours=12),
            note="Wizyta lekarska",
        ))
        await db.commit()
        print("Seed complete.")
        print(f"  admin:   admin@ekorepetycje.pl / admin123")
        print(f"  teacher: anna@ekorepetycje.pl / teacher123")
        print(f"  teacher: marek@ekorepetycje.pl / teacher123")
        print(f"  student: student1@example.com / student123")
        print(f"  student: student2@example.com / student123")


if __name__ == "__main__":
    asyncio.run(seed())
