"""Email service — uses Resend when RESEND_API_KEY is configured, otherwise logs."""

import asyncio
import logging
from html import escape

from app.schemas.contact import ContactForm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML email builders
# ---------------------------------------------------------------------------

def _receiver_html(form: ContactForm) -> str:
    """Rich notification email sent to the platform owner."""
    name    = escape(form.name)
    email   = escape(str(form.email))
    subject = escape(form.subject) if form.subject else ""
    message = escape(form.message).replace("\n", "<br>")
    subject_row = f"""
        <tr>
          <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">Temat</td>
          <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{subject}</td>
        </tr>""" if subject else ""

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nowe zapytanie — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Platforma korepetycji</p>
            <h1 style="margin:0;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">Ekorepetycje</h1>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#ffffff;padding:36px 40px">
            <p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#16a34a">Nowe zapytanie</p>
            <h2 style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;line-height:1.3">Ktoś chce się skontaktować!</h2>

            <!-- Sender card -->
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:28px">
              <tr>
                <td style="padding:20px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:6px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">Imię i nazwisko</td>
                      <td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600">{name}</td>
                    </tr>
                    <tr>
                      <td style="padding:6px 0;color:#6b7280;font-size:13px;vertical-align:top">Adres e-mail</td>
                      <td style="padding:6px 0;font-size:13px">
                        <a href="mailto:{email}" style="color:#16a34a;text-decoration:none;font-weight:600">{email}</a>
                      </td>
                    </tr>{subject_row}
                  </table>
                </td>
              </tr>
            </table>

            <!-- Message block -->
            <p style="margin:0 0 10px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#6b7280">Treść wiadomości</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border-left:4px solid #22c55e;border-radius:0 8px 8px 0;margin-bottom:32px">
              <tr>
                <td style="padding:18px 20px;color:#1f2937;font-size:14px;line-height:1.7">{message}</td>
              </tr>
            </table>

            <!-- Reply CTA -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center">
                  <a href="mailto:{email}?subject=Re%3A Ekorepetycje — zapytanie"
                     style="display:inline-block;background:#16a34a;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;padding:13px 32px;border-radius:8px;letter-spacing:0.2px">
                    Odpowiedz na wiadomość
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:11px;color:#9ca3af">Ta wiadomość została wygenerowana automatycznie przez platformę Ekorepetycje.<br>
            Odpowiadaj bezpośrednio na ten e-mail, aby skontaktować się z nadawcą.</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _acknowledgment_html(form: ContactForm) -> str:
    """Warm confirmation email sent back to the person who submitted the form."""
    name    = escape(form.name.split()[0])          # first name only for warmth
    subject = escape(form.subject) if form.subject else "ogólne"
    message = escape(form.message).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Dziękujemy za wiadomość — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:40px 40px 36px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Platforma korepetycji</p>
            <h1 style="margin:0 0 20px;font-size:28px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">Ekorepetycje</h1>
            <!-- Checkmark icon -->
            <div style="display:inline-block;background:rgba(255,255,255,0.15);border-radius:50%;width:56px;height:56px;line-height:56px;text-align:center">
              <span style="font-size:26px">✓</span>
            </div>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#ffffff;padding:40px 40px 32px">
            <h2 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#111827;line-height:1.3">
              Cześć, {name}! 👋
            </h2>
            <p style="margin:0 0 24px;font-size:15px;color:#4b5563;line-height:1.7">
              Dziękujemy za Twoją wiadomość — dotarła do nas i już na nią czekamy!<br>
              Nasz zespół odpowie najszybciej jak to możliwe, zazwyczaj <strong style="color:#111827">w ciągu 24&nbsp;godzin</strong> w dni robocze.
            </p>

            <!-- Summary of what they sent -->
            <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;margin-bottom:32px">
              <tr>
                <td style="padding:6px 24px 4px;border-bottom:1px solid #dcfce7">
                  <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;color:#16a34a">Twoja wiadomość (kopia)</p>
                </td>
              </tr>
              <tr>
                <td style="padding:16px 24px">
                  <p style="margin:0 0 8px;font-size:12px;color:#6b7280">Temat: <strong style="color:#374151">{subject}</strong></p>
                  <p style="margin:0;font-size:13px;color:#374151;line-height:1.7">{message}</p>
                </td>
              </tr>
            </table>

            <!-- What's next -->
            <p style="margin:0 0 14px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#6b7280">Co dalej?</p>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:10px 0;border-bottom:1px solid #f3f4f6">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="width:32px;vertical-align:top;padding-top:1px">
                        <div style="width:24px;height:24px;background:#dcfce7;border-radius:50%;text-align:center;line-height:24px;font-size:12px;font-weight:700;color:#16a34a">1</div>
                      </td>
                      <td style="padding-left:12px;color:#374151;font-size:14px;line-height:1.5">
                        Przejrzymy Twoją wiadomość i dopasujemy najlepszego korepetytora
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td style="padding:10px 0;border-bottom:1px solid #f3f4f6">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="width:32px;vertical-align:top;padding-top:1px">
                        <div style="width:24px;height:24px;background:#dcfce7;border-radius:50%;text-align:center;line-height:24px;font-size:12px;font-weight:700;color:#16a34a">2</div>
                      </td>
                      <td style="padding-left:12px;color:#374151;font-size:14px;line-height:1.5">
                        Skontaktujemy się z Tobą e-mailem lub telefonicznie, aby omówić szczegóły
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td style="padding:10px 0">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="width:32px;vertical-align:top;padding-top:1px">
                        <div style="width:24px;height:24px;background:#dcfce7;border-radius:50%;text-align:center;line-height:24px;font-size:12px;font-weight:700;color:#16a34a">3</div>
                      </td>
                      <td style="padding-left:12px;color:#374151;font-size:14px;line-height:1.5">
                        Pierwsza lekcja próbna — bez zobowiązań!
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Green band CTA -->
        <tr>
          <td style="background:#16a34a;padding:28px 40px;text-align:center">
            <p style="margin:0 0 16px;font-size:14px;color:#dcfce7;line-height:1.6">
              Masz pilne pytanie? Napisz do nas bezpośrednio:
            </p>
            <a href="mailto:kontakt@ekorepetycje.pl"
               style="display:inline-block;background:#ffffff;color:#16a34a;text-decoration:none;font-size:14px;font-weight:700;padding:11px 28px;border-radius:8px">
              kontakt@ekorepetycje.pl
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:24px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#374151">Ekorepetycje</p>
            <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6">
              Otrzymujesz tę wiadomość, ponieważ wypełniłeś/aś formularz kontaktowy na naszej stronie.<br>
              Jeśli to pomyłka, możesz zignorować tę wiadomość.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_contact_email(form: ContactForm) -> None:
    """Send contact-form notification to the owner AND an acknowledgment to the sender.

    Falls back to logging when RESEND_API_KEY is not set so that local
    development and CI work without any external credentials.
    """
    from app.core.config import settings

    if not settings.RESEND_API_KEY:
        logger.info(
            "Contact form [no RESEND_API_KEY — logging only] | name=%s | email=%s | subject=%s | message=%s",
            form.name, form.email, form.subject, form.message,
        )
        return

    import resend  # noqa: PLC0415 — optional dependency

    resend.api_key = settings.RESEND_API_KEY

    subject_suffix = f" — {form.subject}" if form.subject else ""

    # 1. Notification to the platform owner
    notification = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [settings.RESEND_TO_EMAIL],
        "reply_to": [str(form.email)],
        "subject": f"Nowe zapytanie od {form.name}{subject_suffix}",
        "html": _receiver_html(form),
    }

    # 2. Acknowledgment to the person who submitted the form
    acknowledgment = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [str(form.email)],
        "subject": "Dziękujemy za wiadomość — Ekorepetycje",
        "html": _acknowledgment_html(form),
    }

    # Send both concurrently — run_in_executor since resend SDK is synchronous
    await asyncio.gather(
        asyncio.to_thread(resend.Emails.send, notification),
        asyncio.to_thread(resend.Emails.send, acknowledgment),
    )
    logger.info(
        "Contact emails sent | owner=%s | sender=%s",
        settings.RESEND_TO_EMAIL, form.email,
    )


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
