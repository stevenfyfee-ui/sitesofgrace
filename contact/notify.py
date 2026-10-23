"""
The staff alert for a new contact message.

Sent to staff only -- NEVER to the sender, whose address is only the
Reply-To. Goes through Django's configured EMAIL_BACKEND (Anymail/Resend in
production). A failure is logged and swallowed: the message is already
saved, and the visitor still sees the thank-you.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

logger = logging.getLogger(__name__)


def _one_line(value):
    """A header-safe value: no CR, LF, or other line breaks."""
    return " ".join(str(value or "").split())


def recipients_for(message):
    """[address] for this message's alert, or [] when none is configured."""
    if message.topic == "billing" and settings.SUPPORT_EMAIL:
        return [settings.SUPPORT_EMAIL]
    for address in (getattr(settings, "CONTACT_EMAIL", ""), settings.MODERATION_EMAIL):
        if address:
            return [address]
    return [address for _, address in settings.ADMINS if address]


def _admin_url(message):
    path = reverse("contact_messages:edit", args=[message.pk])
    return settings.WAGTAILADMIN_BASE_URL.rstrip("/") + path


def alert_body(message):
    """The alert text. A prayer request's text is left out -- it's read in
    the admin, so no copy outlives its 90 days in a mailbox."""
    lines = [
        f"Topic: {message.get_topic_display()}",
        f"Name: {message.name}",
        f"Email: {message.email}",
    ]
    if not message.is_prayer:
        if message.related_page_id:
            page = message.related_page
            lines.append(f"Related page: {page.title} ({page.full_url or page.url_path})")
        lines += ["", message.message]
    lines += ["", f"Open in the admin: {_admin_url(message)}"]
    return "\n".join(lines)


def send_staff_alert(message):
    """Email staff about `message`. Returns True if it was handed to the
    mail backend."""
    to = recipients_for(message)
    if not to:
        logger.warning(
            "Contact message %s saved, but no alert was sent: CONTACT_EMAIL, "
            "MODERATION_EMAIL, and ADMINS are all empty.", message.pk,
        )
        return False
    email = EmailMessage(
        subject=_one_line(f"[Sites of Grace] {message.get_topic_display()}: {message.name}"),
        body=alert_body(message),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
        reply_to=[_one_line(message.email)],
    )
    try:
        email.send()
    except Exception:
        logger.exception("Couldn't send the staff alert for contact message %s.", message.pk)
        return False
    return True
