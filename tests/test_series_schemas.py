"""Tests for RecurringSeries Pydantic schemas."""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.series import RecurringSeriesCreate, DaySlot


def test_day_slot_valid():
    slot = DaySlot(day=0, hour=17, minute=0, duration_minutes=60)
    assert slot.day == 0
    assert slot.duration_minutes == 60


def test_day_slot_invalid_day():
    with pytest.raises(ValidationError):
        DaySlot(day=7, hour=17, minute=0, duration_minutes=60)


def test_series_create_requires_one_end_condition():
    """Exactly one of end_date/end_count must be set."""
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
            end_date=None,
            end_count=None,
        )


def test_series_create_both_end_conditions_invalid():
    """Both end_date and end_count set — invalid."""
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[DaySlot(day=0, hour=17, minute=0, duration_minutes=60)],
            end_date=date(2026, 6, 30),
            end_count=10,
        )


def test_series_create_no_slots_invalid():
    with pytest.raises(ValidationError):
        RecurringSeriesCreate(
            teacher_id=uuid.uuid4(),
            offering_id=uuid.uuid4(),
            title="Math",
            start_date=date(2026, 4, 7),
            interval_weeks=1,
            day_slots=[],
            end_count=10,
        )
