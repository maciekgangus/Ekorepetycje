import pytest
from httpx import AsyncClient, ASGITransport

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


async def test_get_login_page_returns_200():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/login")
    assert r.status_code == 200
    assert "Zaloguj" in r.text


async def test_login_wrong_credentials_returns_form_with_error():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/login", data={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 200
    assert "Nieprawidłowy" in r.text
