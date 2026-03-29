"""add_event_change_requests_table

Revision ID: d4260c02a08c
Revises: 768151a670c1
Create Date: 2026-03-29 19:12:34.457297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4260c02a08c'
down_revision: Union[str, Sequence[str], None] = '768151a670c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_schedule_events_student_start'), table_name='schedule_events')
    op.drop_index(op.f('ix_schedule_events_teacher_start'), table_name='schedule_events')
    op.create_table(
        "event_change_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("proposer_id", sa.UUID(), nullable=False),
        sa.Column("responder_id", sa.UUID(), nullable=False),
        sa.Column("new_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "rejected", "cancelled",
                    name="changerequeststatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["schedule_events.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["responder_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ecr_event_id", "event_change_requests", ["event_id"])
    op.create_index("ix_ecr_proposer_id", "event_change_requests", ["proposer_id"])
    op.create_index("ix_ecr_responder_id", "event_change_requests", ["responder_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ecr_responder_id", table_name="event_change_requests")
    op.drop_index("ix_ecr_proposer_id", table_name="event_change_requests")
    op.drop_index("ix_ecr_event_id", table_name="event_change_requests")
    op.drop_table("event_change_requests")
    op.execute("DROP TYPE IF EXISTS changerequeststatus")
    op.create_index(op.f('ix_schedule_events_teacher_start'), 'schedule_events', ['teacher_id', 'start_time'], unique=False)
    op.create_index(op.f('ix_schedule_events_student_start'), 'schedule_events', ['student_id', 'start_time'], unique=False)
