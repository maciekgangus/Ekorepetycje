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
    # --- Enums ---
    userrole_enum = sa.Enum("admin", "teacher", "student", name="userrole")
    eventstatus_enum = sa.Enum("scheduled", "completed", "cancelled", name="eventstatus")
    userrole_enum.create(op.get_bind(), checkfirst=True)
    eventstatus_enum.create(op.get_bind(), checkfirst=True)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Enum("admin", "teacher", "student", name="userrole"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # --- offerings ---
    op.create_table(
        "offerings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price_per_hour", sa.Numeric(10, 2), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- schedule_events ---
    op.create_table(
        "schedule_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offering_id", sa.UUID(), nullable=False),
        sa.Column("teacher_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("scheduled", "completed", "cancelled", name="eventstatus"),
            nullable=False,
            server_default="scheduled",
        ),
        sa.ForeignKeyConstraint(["offering_id"], ["offerings.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("schedule_events")
    op.drop_table("offerings")
    op.drop_table("users")
    sa.Enum(name="eventstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
