"""add_event_time_indexes

Revision ID: 768151a670c1
Revises: 698e615463d4
Create Date: 2026-03-29 13:31:28.258988

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '768151a670c1'
down_revision: Union[str, Sequence[str], None] = '698e615463d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_schedule_events_teacher_start',
        'schedule_events', ['teacher_id', 'start_time'],
    )
    op.create_index(
        'ix_schedule_events_student_start',
        'schedule_events', ['student_id', 'start_time'],
    )


def downgrade() -> None:
    op.drop_index('ix_schedule_events_student_start', table_name='schedule_events')
    op.drop_index('ix_schedule_events_teacher_start', table_name='schedule_events')
