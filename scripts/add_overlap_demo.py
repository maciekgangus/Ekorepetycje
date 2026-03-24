"""Add 5 simultaneous events on Saturday 2026-03-28 at 10:00–11:30 — one per teacher."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.users import User, UserRole
from app.models.offerings import Offering
from app.models.scheduling import ScheduleEvent, EventStatus

DATABASE_URL = "postgresql+asyncpg://postgres:password@db:5432/ekorepetycje"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main():
    async with AsyncSessionLocal() as db:
        teachers = (await db.execute(
            select(User).where(User.role == UserRole.TEACHER).order_by(User.full_name)
        )).scalars().all()

        students = (await db.execute(
            select(User).where(User.role == UserRole.STUDENT).order_by(User.full_name)
        )).scalars().all()

        start = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 3, 28, 11, 30, 0, tzinfo=timezone.utc)

        for i, teacher in enumerate(teachers):
            offering = (await db.execute(
                select(Offering).where(Offering.teacher_id == teacher.id).limit(1)
            )).scalar_one()
            student = students[i % len(students)]

            ev = ScheduleEvent(
                id=uuid.uuid4(),
                title=offering.title,
                start_time=start,
                end_time=end,
                offering_id=offering.id,
                teacher_id=teacher.id,
                student_id=student.id,
                status=EventStatus.SCHEDULED,
            )
            db.add(ev)
            print(f"  {teacher.full_name:25s} → {offering.title}")

        await db.commit()
        print(f"\n✓ 5 overlapping events created on 2026-03-28 10:00–11:30")


if __name__ == "__main__":
    asyncio.run(main())
