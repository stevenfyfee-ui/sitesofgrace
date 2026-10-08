from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="hello@example.com",
)
class SendTestEmailCommandTests(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_sends_one_message_and_reports_success(self):
        out = StringIO()
        call_command("send_test_email", "pilgrim@example.com", stdout=out)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["pilgrim@example.com"])
        self.assertEqual(sent.from_email, "hello@example.com")

        output = out.getvalue()
        self.assertIn("EMAIL_BACKEND", output)
        self.assertIn("Sent to pilgrim@example.com", output)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend",
    )
    def test_reports_the_error_when_the_backend_rejects_the_address(self):
        # The dummy backend "succeeds" without sending, so force a failure
        # the same way a real backend would: patch send_mail to raise.
        from unittest import mock

        with mock.patch(
            "core.management.commands.send_test_email.send_mail",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(CommandError):
                call_command("send_test_email", "pilgrim@example.com")
