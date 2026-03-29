"""Bilateral reschedule proposal tests."""

def test_model_imports():
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    assert ChangeRequestStatus.PENDING == "pending"
    assert ChangeRequestStatus.ACCEPTED == "accepted"
    assert ChangeRequestStatus.REJECTED == "rejected"
    assert ChangeRequestStatus.CANCELLED == "cancelled"


def test_schema_imports():
    from app.schemas.change_requests import EventChangeRequestCreate, EventChangeRequestRead
    import uuid
    from datetime import datetime, timezone
    create = EventChangeRequestCreate(
        event_id=uuid.uuid4(),
        new_start=datetime.now(timezone.utc),
        new_end=datetime.now(timezone.utc),
        note="test",
    )
    assert create.note == "test"
