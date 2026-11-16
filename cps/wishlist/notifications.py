# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Best-effort email notifications for wishlist events."""

import threading

from .. import config, logger, ub
from ..tasks.mail import TaskEmail

log = logger.create()


def send_email(subject, text, recipients):
    if not config.get_mail_server_configured():
        return
    recipients = [recipient for recipient in recipients if recipient]
    if not recipients:
        return
    settings = config.get_mail_settings()

    def deliver():
        for recipient in recipients:
            try:
                TaskEmail(
                    subject,
                    None,
                    None,
                    settings,
                    recipient,
                    "",
                    text,
                ).run(None)
            except Exception as exc:
                log.warning("Could not send wishlist notification to %s: %s", recipient, exc)

    threading.Thread(target=deliver, daemon=True).start()


def admin_emails():
    return [
        user.email
        for user in ub.session.query(ub.User).all()
        if user.email and user.role_admin()
    ]


def notify_request(event, request, note=""):
    title = request.title
    kind = request.content_type.title()
    requester = request.requester.name if request.requester else "A user"
    if event == "created":
        send_email(
            f"New {kind.lower()} request: {title}",
            f"{requester} requested {kind.lower()} “{title}”.\n\n"
            f"Note: {request.note or '—'}\n",
            admin_emails(),
        )
        return
    recipients = [request.requester.email] if request.requester and request.requester.email else []
    if event == "approved":
        subject = f"Request approved: {title}"
        body = f"Your {kind.lower()} request “{title}” was approved."
    elif event == "rejected":
        subject = f"Request declined: {title}"
        body = f"Your {kind.lower()} request “{title}” was declined."
    elif event == "fulfilled":
        subject = f"Request fulfilled: {title}"
        body = f"Your {kind.lower()} request “{title}” was added to the library."
    else:
        return
    if note:
        body += f"\n\nNote: {note}"
    send_email(subject, body + "\n", recipients)
