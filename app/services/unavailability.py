"""Recurring unavailability generation service.

Pure Python — no DB calls. Mirrors generate_events() in services/series.py but
produces UnavailableBlock instances instead of ScheduleEvent instances.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.availability import UnavailableBlock
from app.schemas.unavailability import RecurringUnavailCreate

_MAX_BLOCKS = 200


def generate_unavailable_blocks(
    payload: RecurringUnavailCreate,
    series_id: uuid.UUID,
) -> list[UnavailableBlock]:
    """Expand a recurrence rule into UnavailableBlock instances.

    Algorithm is identical to generate_events():
    - Anchor to the Monday of start_date's ISO week.
    - Walk forward by interval_weeks each iteration.
    - Sort slots by (day, hour, minute) so end_count cuts off chronologically.
    - Raise ValueError if generation would exceed _MAX_BLOCKS.
    """
    sd = payload.start_date
    week_monday = sd - timedelta(days=sd.weekday())

    blocks: list[UnavailableBlock] = []
    week_offset = 0
    sorted_slots = sorted(payload.day_slots, key=lambda s: (s.day, s.hour, s.minute))

    while True:
        current_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)

        for slot in sorted_slots:
            slot_date = current_monday + timedelta(days=slot.day)
            slot_start = datetime(
                slot_date.year, slot_date.month, slot_date.day,
                slot.hour, slot.minute, tzinfo=timezone.utc,
            )
            slot_end = slot_start + timedelta(minutes=slot.duration_minutes)

            if payload.end_date is not None and slot_date > payload.end_date:
                continue
            if payload.end_count is not None and len(blocks) >= payload.end_count:
                break
            if len(blocks) >= _MAX_BLOCKS:
                raise ValueError(
                    f"Series would generate more than {_MAX_BLOCKS} blocks. "
                    "Reduce the duration or increase the interval."
                )

            blocks.append(
                UnavailableBlock(
                    user_id=payload.user_id,
                    series_id=series_id,
                    start_time=slot_start,
                    end_time=slot_end,
                    note=payload.note,
                )
            )

        week_offset += 1

        if payload.end_count is not None and len(blocks) >= payload.end_count:
            break
        if payload.end_date is not None:
            next_monday = week_monday + timedelta(weeks=week_offset * payload.interval_weeks)
            if next_monday > payload.end_date:
                break

    blocks.sort(key=lambda b: b.start_time)
    return blocks
