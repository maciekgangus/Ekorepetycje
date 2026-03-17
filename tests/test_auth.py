from app.core.auth import sign_session, read_session


def test_sign_and_read_roundtrip():
    payload = {"user_id": "abc-123", "role": "admin"}
    token = sign_session(payload)
    assert isinstance(token, str)
    result = read_session(token)
    assert result == payload


def test_read_tampered_token_returns_none():
    result = read_session("tampered.garbage.token")
    assert result is None


def test_read_empty_token_returns_none():
    assert read_session("") is None
    assert read_session(None) is None
