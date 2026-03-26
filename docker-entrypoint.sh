#!/bin/bash
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Checking seed status..."
USER_COUNT=$(python - <<'EOF'
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def count():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM users"))
        print(r.scalar())
    await engine.dispose()

asyncio.run(count())
EOF
)

if [ "${USER_COUNT:-0}" = "0" ]; then
    echo "==> Seeding demo data..."
    PYTHONPATH=/app python scripts/seed_demo.py
else
    echo "==> Database already has ${USER_COUNT} users — skipping seed."
fi

echo "==> Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
