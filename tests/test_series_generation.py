"""Unit tests for the series generation service."""
import uuid
from datetime import date, datetime, timezone, timedelta

import pytest

from app.schemas.series import RecurringSeriesCreate, DaySlot
from app.services.series import generate_events


OFFERING_ID = uuid.uuid4()
TEACHER_ID = uuid.uuid4()
SERIES_ID = uuid.uuid4()


def _base_payload(**kwargs) -> RecurringSeriesCreate:
    defaults = dict(
        teacher_id=TEACHER_ID,
        offering_id=OFFERING_ID,
        title="Matematyka",
        start_date=date(2026, 4, 6),  # Monday
        interval_weeks=1,
        day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
        end_count=4,
    )
    defaults.update(kwargs)
    return RecurringSeriesCreate(**defaults)


def test_weekly_by_count_generates_correct_count():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    assert len(events) == 4


def test_weekly_by_count_correct_days():
    """Events should all be on Monday (day=0)."""
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        assert ev.start_time.weekday() == 0  # Monday


def test_weekly_by_count_correct_time():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        assert ev.start_time.hour == 17
        assert ev.start_time.minute == 0


def test_weekly_by_count_correct_duration():
    events = generate_events(_base_payload(end_count=4), SERIES_ID)
    for ev in events:
        delta = ev.end_time - ev.start_time
        assert delta == timedelta(minutes=60)


def test_weekly_interval_spacing():
    """Consecutive events should be exactly 7 days apart."""
    events = generate_events(_base_payload(end_count=3), SERIES_ID)
    gap = events[1].start_time - events[0].start_time
    assert gap == timedelta(weeks=1)


def test_biweekly_interval_spacing():
    events = generate_events(_base_payload(interval_weeks=2, end_count=3), SERIES_ID)
    gap = events[1].start_time - events[0].start_time
    assert gap == timedelta(weeks=2)


def test_weekly_by_end_date():
    """With end_date, stop before exceeding it."""
    payload = _base_payload(
        end_count=None,
        end_date=date(2026, 4, 27),  # 4 Mondays: Apr 6, 13, 20, 27
        day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
    )
    events = generate_events(payload, SERIES_ID)
    assert len(events) == 4
    assert events[-1].start_time.date() == date(2026, 4, 27)


def test_multi_slot_generates_multiple_events_per_week():
    """Two slots per week → 2 events per week iteration."""
    payload = _base_payload(
        end_count=6,
        day_slots=[
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),  # Monday
            DaySlot(day=3, hour=18, minute=30, duration_minutes=45),  # Thursday
        ],
    )
    events = generate_events(payload, SERIES_ID)
    assert len(events) == 6


def test_multi_slot_different_days():
    payload = _base_payload(
        end_count=4,
        day_slots=[
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),
            DaySlot(day=3, hour=18, minute=30, duration_minutes=45),
        ],
    )
    events = generate_events(payload, SERIES_ID)
    weekdays = [ev.start_time.weekday() for ev in events]
    assert 0 in weekdays  # Monday present
    assert 3 in weekdays  # Thursday present


def test_max_200_cap():
    """Generation raises ValueError if rule would generate more than 200 events."""
    payload = RecurringSeriesCreate.model_construct(
        teacher_id=TEACHER_ID,
        offering_id=OFFERING_ID,
        title="Math",
        start_date=date(2026, 4, 6),
        interval_weeks=1,
        day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
        end_count=201,
        end_date=None,
        student_id=None,
    )
    with pytest.raises(ValueError, match="200"):
        generate_events(payload, SERIES_ID)


def test_events_have_correct_series_id():
    events = generate_events(_base_payload(end_count=3), SERIES_ID)
    for ev in events:
        assert ev.series_id == SERIES_ID


def test_events_are_timezone_aware():
    events = generate_events(_base_payload(end_count=2), SERIES_ID)
    for ev in events:
        assert ev.start_time.tzinfo is not None
        assert ev.end_time.tzinfo is not None


def test_start_date_not_on_monday_anchors_to_week():
    """start_date on Wednesday → first Monday slot is that week's Monday."""
    payload = _base_payload(
        start_date=date(2026, 4, 8),  # Wednesday of week containing Mon Apr 6
        end_count=1,
        day_slots=[DaySlot(day=0, hour=10, minute=0, duration_minutes=60)],
    )
    events = generate_events(payload, SERIES_ID)
    assert events[0].start_time.date() == date(2026, 4, 6)  # Monday of same week


def test_events_sorted_by_start_time():
    """Multi-slot events should be sorted chronologically."""
    payload = _base_payload(
        end_count=4,
        day_slots=[
            DaySlot(day=3, hour=18, minute=0, duration_minutes=60),
            DaySlot(day=0, hour=17, minute=0, duration_minutes=60),
        ],
    )
    events = generate_events(payload, SERIES_ID)
    starts = [ev.start_time for ev in events]
    assert starts == sorted(starts)
