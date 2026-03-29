"""Import all models here so Alembic's autogenerate can discover them."""

from app.db.database import Base  # noqa: F401
from app.models.users import User  # noqa: F401
from app.models.offerings import Offering  # noqa: F401
from app.models.scheduling import ScheduleEvent  # noqa: F401
from app.models.availability import UnavailableBlock  # noqa: F401
from app.models.proposals import RescheduleProposal  # noqa: F401
from app.models.series import RecurringSeries  # noqa: F401
from app.models.unavail_series import RecurringUnavailSeries  # noqa: F401
from app.models.change_requests import EventChangeRequest  # noqa: F401
