"""Series generation service.

Pure Python — no DB calls. Takes a RecurringSeriesCreate payload and a pre-assigned
series UUID, returns a list of ScheduleEvent ORM instances ready to db.add_all().
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.scheduling import ScheduleEvent
from app.schemas.series import RecurringSeriesCreate

_MAX_EVENTS = 200


def generate_events(
    payload: RecurringSeriesCreate,
    series_id: uuid.UUID,
) -> list[ScheduleEvent]:
    """Expand a recurrence rule into ScheduleEvent instances.

    Algorithm:
    - Find the Monday of the ISO week containing payload.start_date.
    - Walk forward week-by-week (step = payload.interval_weeks).
    - For each week, expand every day_slot into a (start, end) datetime pair.
    - Stop when end_count reached or the next slot would exceed end_date.
    - Sort results by start_time.
    - Raise ValueError if generation would exceed _MAX_EVENTS.
    """
    # Anchor to the Monday of start_date's ISO week
    sd = payload.start_date
    week_monday = sd - timedelta(days=sd.weekday())

    events: list[ScheduleEvent] = []
    week_offset = 0
    # Sort slots by day so end_count counts chronologically within each week
    sorted_slots = sorted(payload.day_slots, key=lambda s: (s.day, s.hour, s.minute))

    while True:
        current_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)

        for slot in sorted_slots:
            slot_date = current_monday + timedelta(days=slot.day)
            slot_start = datetime(
                slot_date.year,
                slot_date.month,
                slot_date.day,
                slot.hour,
                slot.minute,
                tzinfo=timezone.utc,
            )
            slot_end = slot_start + timedelta(minutes=slot.duration_minutes)

            # end_date check: skip if this slot's date exceeds end_date
            if payload.end_date is not None and slot_date > payload.end_date:
                continue

            # end_count check: stop if we've already hit the limit
            if payload.end_count is not None and len(events) >= payload.end_count:
                break

            # Hard cap
            if len(events) >= _MAX_EVENTS:
                raise ValueError(
                    f"Series would generate more than {_MAX_EVENTS} events. "
                    "Reduce the duration or increase the interval."
                )

            events.append(
                ScheduleEvent(
                    title=payload.title,
                    start_time=slot_start,
                    end_time=slot_end,
                    offering_id=payload.offering_id,
                    teacher_id=payload.teacher_id,
                    student_id=payload.student_id,
                    series_id=series_id,
                )
            )

        week_offset += 1

        # Termination: by count
        if payload.end_count is not None and len(events) >= payload.end_count:
            break

        # Termination: by date — stop when Monday of current week exceeds end_date
        if payload.end_date is not None:
            next_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)
            if next_monday > payload.end_date:
                break

    events.sort(key=lambda e: e.start_time)
    return events
