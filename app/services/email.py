"""Mock email service for the MVP phase."""

import logging

from app.schemas.contact import ContactForm

logger = logging.getLogger(__name__)


async def send_proposal_email(teacher, proposal) -> None:
    """Stub: log reschedule proposal notifications (full impl in Task 12)."""
    logger.info(
        "Reschedule proposal | teacher=%s | event_id=%s | new_start=%s",
        teacher.full_name, proposal.event_id, proposal.new_start,
    )


async def send_proposal_outcome_email(proposal, approved: bool) -> None:
    """Stub: log proposal outcome notifications (full impl in Task 12)."""
    outcome = "approved" if approved else "rejected"
    logger.info("Proposal outcome=%s | proposal_id=%s", outcome, proposal.id)


async def send_contact_email(form: ContactForm) -> None:
    """Log contact form submissions instead of sending a real email.

    In production this would be replaced with an SMTP or transactional
    email provider (e.g. SendGrid, Resend).
    """
    logger.info(
        "Contact form submission received | name=%s | email=%s | message=%s",
        form.name,
        form.email,
        form.message,
    )
