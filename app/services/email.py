"""Mock email service for the MVP phase."""

import logging

from app.schemas.contact import ContactForm

logger = logging.getLogger(__name__)


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
