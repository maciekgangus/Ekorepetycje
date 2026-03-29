"""drop_reschedule_proposals_table

Revision ID: 18f3e895b0f9
Revises: d4260c02a08c
Create Date: 2026-03-29 19:35:23.732509

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18f3e895b0f9'
down_revision: Union[str, Sequence[str], None] = 'd4260c02a08c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("reschedule_proposals")
    op.execute("DROP TYPE IF EXISTS proposalstatus")


def downgrade() -> None:
    op.create_table(
        "reschedule_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("proposed_by", sa.UUID(), nullable=False),
        sa.Column("new_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="proposalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["schedule_events.id"]),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
