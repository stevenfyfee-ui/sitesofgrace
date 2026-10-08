"""Send a single plain test email through the currently configured backend.

    python manage.py send_test_email you@example.com

Prints which EMAIL_BACKEND is active and the result, or raises the send
error -- a quick way to confirm Resend (or SMTP, or the dev console backend)
is actually wired up without going through the app itself.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one plain test email through the configured EMAIL_BACKEND."

    def add_arguments(self, parser):
        parser.add_argument("address", help="Recipient email address.")

    def handle(self, *args, **options):
        address = options["address"]
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL!r}")

        try:
            sent = send_mail(
                subject="Sites of Grace test email",
                message=(
                    "This is a test message sent by `manage.py send_test_email` "
                    "to confirm the configured email backend is working."
                ),
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[address],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f"Send failed: {exc}") from exc

        if sent:
            self.stdout.write(self.style.SUCCESS(f"Sent to {address} (send_mail returned {sent})."))
        else:
            self.stdout.write(self.style.WARNING(
                f"send_mail returned {sent} -- the backend did not report a delivered message."
            ))
