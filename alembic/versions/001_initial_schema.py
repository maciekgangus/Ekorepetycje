"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-17 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                CREATE TYPE userrole AS ENUM ('admin', 'teacher', 'student');
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'eventstatus') THEN
                CREATE TYPE eventstatus AS ENUM ('scheduled', 'completed', 'cancelled');
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            role userrole NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS offerings (
            id UUID PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            base_price_per_hour NUMERIC(10, 2) NOT NULL,
            teacher_id UUID NOT NULL REFERENCES users(id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_events (
            id UUID PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ NOT NULL,
            offering_id UUID NOT NULL REFERENCES offerings(id),
            teacher_id UUID NOT NULL REFERENCES users(id),
            student_id UUID REFERENCES users(id),
            status eventstatus NOT NULL DEFAULT 'scheduled'
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_events")
    op.execute("DROP TABLE IF EXISTS offerings")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TYPE IF EXISTS eventstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
