from httpx import AsyncClient, ASGITransport
from app.main import app


async def test_admin_users_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/admin/users", follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers["location"]
