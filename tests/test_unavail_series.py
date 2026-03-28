"""Unit tests for generate_unavailable_blocks() in app.services.unavailability.

Mirrors the style of test_series_generation.py — pure function calls, no DB needed.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.schemas.unavailability import RecurringUnavailCreate
from app.schemas.series import DaySlot
from app.services.unavailability import generate_unavailable_blocks

USER_ID = uuid.uuid4()
SERIES_ID = uuid.uuid4()


def _base_payload(**kwargs) -> RecurringUnavailCreate:
    defaults = dict(
        user_id=USER_ID,
        note=None,
        start_date=date(2026, 4, 6),  # Monday
        interval_weeks=1,
        day_slots=[DaySlot(day=0, hour=10, minute=0, duration_minutes=60)],
        end_count=4,
    )
    defaults.update(kwargs)
    return RecurringUnavailCreate(**defaults)


# ── Count-based termination ───────────────────────────────────────────────────

def test_count_generates_correct_number_of_blocks():
    blocks = generate_unavailable_blocks(_base_payload(end_count=4), SERIES_ID)
    assert len(blocks) == 4


def test_count_of_one_generates_exactly_one_block():
    blocks = generate_unavailable_blocks(_base_payload(end_count=1), SERIES_ID)
    assert len(blocks) == 1


# ── Date-based termination ────────────────────────────────────────────────────

def test_date_based_count_is_correct():
    # Monday 6 Apr + weekly Mon slot for 4 weeks → 4 blocks (6 Apr, 13 Apr, 20 Apr, 27 Apr)
    blocks = generate_unavailable_blocks(
        _base_payload(
            start_date=date(2026, 4, 6),
            end_date=date(2026, 4, 27),
            end_count=None,
        ),
        SERIES_ID,
    )
    assert len(blocks) == 4


def test_date_based_stops_at_end_date():
    # end_date is 20 Apr — the slot on 27 Apr must NOT be included
    blocks = generate_unavailable_blocks(
        _base_payload(
            start_date=date(2026, 4, 6),
            end_date=date(2026, 4, 20),
            end_count=None,
        ),
        SERIES_ID,
    )
    last = max(b.start_time.date() for b in blocks)
    assert last <= date(2026, 4, 20)


# ── Interval spacing ──────────────────────────────────────────────────────────

def test_weekly_interval_spacing():
    blocks = generate_unavailable_blocks(_base_payload(end_count=3), SERIES_ID)
    gap = blocks[1].start_time - blocks[0].start_time
    assert gap == timedelta(weeks=1)


def test_biweekly_interval_spacing():
    blocks = generate_unavailable_blocks(_base_payload(interval_weeks=2, end_count=3), SERIES_ID)
    gap = blocks[1].start_time - blocks[0].start_time
    assert gap == timedelta(weeks=2)


# ── Duration ──────────────────────────────────────────────────────────────────

def test_block_duration_matches_slot():
    blocks = generate_unavailable_blocks(
        _base_payload(
            day_slots=[DaySlot(day=0, hour=9, minute=0, duration_minutes=90)],
            end_count=2,
        ),
        SERIES_ID,
    )
    for b in blocks:
        assert b.end_time - b.start_time == timedelta(minutes=90)


# ── Multi-slot ────────────────────────────────────────────────────────────────

def test_multi_slot_per_week_multiplies_block_count():
    """Two slots per week × 3 weeks = 6 blocks."""
    blocks = generate_unavailable_blocks(
        _base_payload(
            day_slots=[
                DaySlot(day=0, hour=9, minute=0, duration_minutes=60),
                DaySlot(day=2, hour=14, minute=0, duration_minutes=60),
            ],
            end_count=6,
        ),
        SERIES_ID,
    )
    assert len(blocks) == 6


def test_multi_slot_different_days():
    """Slots on Mon (day=0) and Wed (day=2) must land on correct weekdays."""
    blocks = generate_unavailable_blocks(
        _base_payload(
            day_slots=[
                DaySlot(day=0, hour=9, minute=0, duration_minutes=60),
                DaySlot(day=2, hour=14, minute=0, duration_minutes=60),
            ],
            end_count=4,
        ),
        SERIES_ID,
    )
    weekdays = [b.start_time.weekday() for b in blocks]
    assert 0 in weekdays  # Monday
    assert 2 in weekdays  # Wednesday


# ── Cap / overflow protection ─────────────────────────────────────────────────

def test_exceeding_max_blocks_raises_value_error():
    """200+ blocks must raise ValueError, not silently truncate."""
    with pytest.raises(ValueError, match="200"):
        generate_unavailable_blocks(
            _base_payload(end_count=201),
            SERIES_ID,
        )


# ── Timezone awareness ────────────────────────────────────────────────────────

def test_blocks_are_utc_timezone_aware():
    blocks = generate_unavailable_blocks(_base_payload(end_count=3), SERIES_ID)
    for b in blocks:
        assert b.start_time.tzinfo is not None
        assert b.start_time.tzinfo == timezone.utc
        assert b.end_time.tzinfo is not None


# ── Day-of-week correctness ───────────────────────────────────────────────────

def test_monday_slot_on_correct_weekday():
    """day=0 → Monday (weekday() == 0)."""
    blocks = generate_unavailable_blocks(
        _base_payload(day_slots=[DaySlot(day=0, hour=10, minute=0, duration_minutes=60)], end_count=3),
        SERIES_ID,
    )
    for b in blocks:
        assert b.start_time.weekday() == 0


def test_friday_slot_on_correct_weekday():
    """day=4 → Friday (weekday() == 4)."""
    blocks = generate_unavailable_blocks(
        _base_payload(
            day_slots=[DaySlot(day=4, hour=10, minute=0, duration_minutes=60)],
            end_count=3,
        ),
        SERIES_ID,
    )
    for b in blocks:
        assert b.start_time.weekday() == 4


# ── Sorted output ─────────────────────────────────────────────────────────────

def test_output_is_sorted_chronologically():
    blocks = generate_unavailable_blocks(
        _base_payload(
            day_slots=[
                DaySlot(day=4, hour=10, minute=0, duration_minutes=60),
                DaySlot(day=0, hour=10, minute=0, duration_minutes=60),
            ],
            end_count=6,
        ),
        SERIES_ID,
    )
    times = [b.start_time for b in blocks]
    assert times == sorted(times)


# ── user_id and note propagation ─────────────────────────────────────────────

def test_user_id_set_on_blocks():
    blocks = generate_unavailable_blocks(_base_payload(end_count=2), SERIES_ID)
    for b in blocks:
        assert b.user_id == USER_ID


def test_note_propagated_to_blocks():
    blocks = generate_unavailable_blocks(_base_payload(note="Urlop", end_count=2), SERIES_ID)
    for b in blocks:
        assert b.note == "Urlop"


def test_series_id_set_on_blocks():
    blocks = generate_unavailable_blocks(_base_payload(end_count=2), SERIES_ID)
    for b in blocks:
        assert b.series_id == SERIES_ID
