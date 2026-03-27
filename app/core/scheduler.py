"""APScheduler setup — AsyncIOScheduler wired into FastAPI lifespan."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="UTC")


def setup_scheduler() -> None:
    """Register all recurring jobs."""
    from app.services.reminders import send_lesson_reminders

    scheduler.add_job(
        send_lesson_reminders,
        trigger="interval",
        minutes=1,
        id="lesson_reminders",
        replace_existing=True,
        max_instances=1,        # never overlap if a run takes > 1 min
        misfire_grace_time=30,  # skip if delayed by ≤ 30 s
    )
