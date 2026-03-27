"""Lesson reminder service — called every minute by APScheduler.

Finds ScheduleEvents starting in 13–16 minutes that haven't been notified
yet, sends an HTML email to both teacher and student, then stamps
reminder_sent_at so the job never fires twice for the same event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.scheduling import ScheduleEvent, EventStatus

logger = logging.getLogger(__name__)

# Window: 13 min ≤ time_until_start ≤ 16 min
_WINDOW_EARLY = timedelta(minutes=13)
_WINDOW_LATE  = timedelta(minutes=16)


# ---------------------------------------------------------------------------
# HTML email builders
# ---------------------------------------------------------------------------

def _fmt_time(dt: datetime) -> str:
    """Return Polish-friendly 'DD.MM.YYYY o HH:MM'."""
    local = dt.astimezone()   # container TZ; UTC in Docker → append 'UTC'
    return local.strftime("%-d.%-m.%Y o %H:%M")


def _teacher_html(event: ScheduleEvent) -> str:
    teacher_name = escape(event.teacher.full_name)
    student_name = escape(event.student.full_name) if event.student else "Uczeń"
    title        = escape(event.title)
    when         = _fmt_time(event.start_time)

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Lekcja za 15 minut — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Ekorepetycje</p>
            <h1 style="margin:0 0 6px;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">⏰ Lekcja za 15 minut</h1>
            <p style="margin:0;font-size:15px;color:#dcfce7">Przygotuj się — za chwilę zaczyna się zajęcie</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#ffffff;padding:36px 40px">
            <p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#16a34a">Przypomnienie</p>
            <h2 style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;letter-spacing:-0.3px">
              Cześć, {teacher_name}!
            </h2>
            <p style="margin:0 0 28px;font-size:15px;color:#374151;line-height:1.6">
              Już za <strong>15 minut</strong> masz zaplanowaną lekcję z <strong>{student_name}</strong>. Oto szczegóły:
            </p>

            <!-- Details card -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:0;margin-bottom:28px">
              <tr>
                <td style="padding:20px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">📅 Termin</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{when}</td>
                    </tr>
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;vertical-align:top">📚 Przedmiot</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{title}</td>
                    </tr>
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;vertical-align:top">👤 Uczeń</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{student_name}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- CTA -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center">
                  <a href="https://ekorepetycje.lesniakmaciek.dev/teacher/dashboard"
                     style="display:inline-block;background:#16a34a;color:#ffffff;font-size:15px;font-weight:600;
                            padding:14px 32px;border-radius:8px;text-decoration:none;letter-spacing:-0.1px">
                    Otwórz panel nauczyciela →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:12px;color:#9ca3af">
              Ekorepetycje &mdash; platforma korepetycji online<br>
              To powiadomienie zostało wysłane automatycznie.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _student_html(event: ScheduleEvent) -> str:
    teacher_name = escape(event.teacher.full_name)
    student_name = escape(event.student.full_name) if event.student else "Uczniu"
    title        = escape(event.title)
    when         = _fmt_time(event.start_time)

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Twoja lekcja za 15 minut — Ekorepetycje</title>
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;padding:40px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);border-radius:16px 16px 0 0;padding:32px 40px;text-align:center">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#bbf7d0">Ekorepetycje</p>
            <h1 style="margin:0 0 6px;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.3px">🎓 Lekcja za 15 minut!</h1>
            <p style="margin:0;font-size:15px;color:#dcfce7">Twoje zajęcia zaczynają się już za chwilę</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="background:#ffffff;padding:36px 40px">
            <p style="margin:0 0 6px;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#16a34a">Przypomnienie o lekcji</p>
            <h2 style="margin:0 0 24px;font-size:22px;font-weight:700;color:#111827;letter-spacing:-0.3px">
              Cześć, {student_name}!
            </h2>
            <p style="margin:0 0 28px;font-size:15px;color:#374151;line-height:1.6">
              Twoja lekcja z <strong>{teacher_name}</strong> zaczyna się za <strong>15 minut</strong>. Gotowy?
            </p>

            <!-- Details card -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:0;margin-bottom:28px">
              <tr>
                <td style="padding:20px 24px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;width:120px;vertical-align:top">📅 Termin</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{when}</td>
                    </tr>
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;vertical-align:top">📚 Przedmiot</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{title}</td>
                    </tr>
                    <tr>
                      <td style="padding:7px 0;color:#6b7280;font-size:13px;vertical-align:top">👩‍🏫 Nauczyciel</td>
                      <td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">{teacher_name}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- Motivational band -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f0fdf4;border-left:4px solid #16a34a;border-radius:0 8px 8px 0;margin-bottom:28px">
              <tr>
                <td style="padding:14px 20px">
                  <p style="margin:0;font-size:14px;color:#15803d;font-weight:500;line-height:1.5">
                    💡 Przygotuj zeszyt, podręcznik lub zadania, które chcesz omówić — dobra lekcja zaczyna się od przygotowania!
                  </p>
                </td>
              </tr>
            </table>

            <!-- CTA -->
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center">
                  <a href="https://ekorepetycje.lesniakmaciek.dev/student/calendar"
                     style="display:inline-block;background:#16a34a;color:#ffffff;font-size:15px;font-weight:600;
                            padding:14px 32px;border-radius:8px;text-decoration:none;letter-spacing:-0.1px">
                    Zobacz swój kalendarz →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-radius:0 0 16px 16px;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb">
            <p style="margin:0;font-size:12px;color:#9ca3af">
              Ekorepetycje &mdash; platforma korepetycji online<br>
              To powiadomienie zostało wysłane automatycznie.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Sending helper (reuses Resend or logs like the contact form)
# ---------------------------------------------------------------------------

async def _send(to: str, subject: str, html: str) -> None:
    import os
    api_key = os.environ.get("RESEND_API_KEY", "")
    from_addr = os.environ.get("RESEND_FROM_EMAIL", "Ekorepetycje <noreply@ekorepetycje.pl>")

    if not api_key:
        logger.info("REMINDER (no key) → %s | %s", to, subject)
        return

    import resend
    resend.api_key = api_key
    try:
        resend.Emails.send({"from": from_addr, "to": [to], "subject": subject, "html": html})
        logger.info("Reminder sent → %s", to)
    except Exception as exc:
        logger.error("Failed to send reminder to %s: %s", to, exc)


# ---------------------------------------------------------------------------
# Main job — called every minute by APScheduler
# ---------------------------------------------------------------------------

async def send_lesson_reminders() -> None:
    """Query for lessons starting in ~15 min and email teacher + student."""
    now   = datetime.now(timezone.utc)
    early = now + _WINDOW_EARLY
    late  = now + _WINDOW_LATE

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduleEvent)
            .where(
                ScheduleEvent.status == EventStatus.SCHEDULED,
                ScheduleEvent.reminder_sent_at.is_(None),
                ScheduleEvent.start_time >= early,
                ScheduleEvent.start_time <= late,
            )
            .options(
                selectinload(ScheduleEvent.teacher),
                selectinload(ScheduleEvent.student),
            )
        )
        events = result.scalars().all()

        if not events:
            return

        logger.info("Sending reminders for %d event(s)", len(events))

        for event in events:
            sends = []

            # Teacher
            if event.teacher and event.teacher.email:
                sends.append(_send(
                    to      = event.teacher.email,
                    subject = f"⏰ Lekcja za 15 minut — {event.student.full_name if event.student else 'uczeń'}",
                    html    = _teacher_html(event),
                ))

            # Student
            if event.student and event.student.email:
                sends.append(_send(
                    to      = event.student.email,
                    subject = "🎓 Twoja lekcja zaczyna się za 15 minut!",
                    html    = _student_html(event),
                ))

            import asyncio
            await asyncio.gather(*sends)

            # Stamp so we never send twice
            event.reminder_sent_at = now
            await db.commit()
