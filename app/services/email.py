"""Email service — uses Resend when RESEND_API_KEY is configured, otherwise logs."""

import asyncio
import logging

from app.schemas.contact import ContactForm

logger = logging.getLogger(__name__)


async def send_contact_email(form: ContactForm) -> None:
    """Send a contact-form submission email via Resend.

    Falls back to logging when RESEND_API_KEY is not set so that local
    development and CI work without any external credentials.
    """
    # Import here to avoid loading settings at module level during tests
    from app.core.config import settings

    if not settings.RESEND_API_KEY:
        logger.info(
            "Contact form [no RESEND_API_KEY — logging only] | name=%s | email=%s | subject=%s | message=%s",
            form.name, form.email, form.subject, form.message,
        )
        return

    import resend  # noqa: PLC0415 — optional dependency

    resend.api_key = settings.RESEND_API_KEY

    subject_line = f"Nowe zapytanie od {form.name}"
    if form.subject:
        subject_line += f" — {form.subject}"

    html_body = f"""
    <p><strong>Imię i nazwisko:</strong> {form.name}</p>
    <p><strong>E-mail:</strong> {form.email}</p>
    {"<p><strong>Przedmiot:</strong> " + form.subject + "</p>" if form.subject else ""}
    <p><strong>Wiadomość:</strong></p>
    <p style="white-space:pre-wrap">{form.message}</p>
    """

    # resend SDK is synchronous — run in a thread to avoid blocking the event loop.
    await asyncio.to_thread(
        resend.Emails.send,
        {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [settings.RESEND_TO_EMAIL],
            "reply_to": [form.email],
            "subject": subject_line,
            "html": html_body,
        },
    )
    logger.info("Contact email sent via Resend | to=%s | from=%s", settings.RESEND_TO_EMAIL, form.email)


async def send_proposal_email(teacher, proposal) -> None:
    """Stub: log reschedule proposal notifications."""
    logger.info(
        "Reschedule proposal | teacher=%s | event_id=%s | new_start=%s",
        teacher.full_name, proposal.event_id, proposal.new_start,
    )


async def send_proposal_outcome_email(proposal, approved: bool) -> None:
    """Stub: log proposal outcome notifications."""
    outcome = "approved" if approved else "rejected"
    logger.info("Proposal outcome=%s | proposal_id=%s", outcome, proposal.id)
