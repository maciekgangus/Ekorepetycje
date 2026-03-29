"""Bilateral reschedule proposal tests."""

def test_model_imports():
    from app.models.change_requests import EventChangeRequest, ChangeRequestStatus
    assert ChangeRequestStatus.PENDING == "pending"
    assert ChangeRequestStatus.ACCEPTED == "accepted"
    assert ChangeRequestStatus.REJECTED == "rejected"
    assert ChangeRequestStatus.CANCELLED == "cancelled"
