"""Tests for the Resend/Anymail wiring in sitesofgrace.settings.production.

production.py is a real settings module, not something the test suite is
running under (tests run under settings.dev). Each test imports it directly
with the environment variables it reads patched, after clearing any
previously-imported copy -- the whole point here is the decision production.py
makes at import time, so it has to be re-evaluated fresh every time.
"""
import importlib
import sys
from unittest import mock

from django.test import SimpleTestCase

_MODULE = "sitesofgrace.settings.production"

# The minimum production.py needs to import without raising -- none of it is
# a real secret or a real database.
_BASE_ENV = {
    "SECRET_KEY": "test-secret-key",
    "DATABASE_URL": "postgres://user:pass@127.0.0.1:5432/testdb",
    "ALLOWED_HOSTS": "example.com",
    "SPACES_BUCKET": "test-bucket",
}


def _import_production(env_overrides):
    env = {**_BASE_ENV, **env_overrides}
    sys.modules.pop(_MODULE, None)
    with mock.patch.dict("os.environ", env, clear=True):
        return importlib.import_module(_MODULE)


class ResendEmailBackendTests(SimpleTestCase):
    def tearDown(self):
        # Leave no imported copy behind to confuse a later test module.
        sys.modules.pop(_MODULE, None)

    def test_anymail_backend_used_when_resend_api_key_set(self):
        settings_mod = _import_production({
            "RESEND_API_KEY": "re_fake_key",
            "DEFAULT_FROM_EMAIL": "hello@example.com",
        })
        self.assertEqual(settings_mod.EMAIL_BACKEND, "anymail.backends.resend.EmailBackend")
        self.assertEqual(settings_mod.ANYMAIL, {"RESEND_API_KEY": "re_fake_key"})
        self.assertEqual(settings_mod.DEFAULT_FROM_EMAIL, "hello@example.com")

    def test_fallback_backend_and_warning_when_resend_api_key_unset(self):
        with self.assertLogs(_MODULE, level="WARNING") as cm:
            settings_mod = _import_production({})
        self.assertEqual(settings_mod.EMAIL_BACKEND, "django.core.mail.backends.smtp.EmailBackend")
        self.assertFalse(hasattr(settings_mod, "ANYMAIL"))
        self.assertTrue(any("RESEND_API_KEY is not set" in msg for msg in cm.output))

    def test_warning_suppressed_during_collectstatic(self):
        with mock.patch.object(sys, "argv", ["manage.py", "collectstatic", "--noinput"]):
            # assertNoLogs isn't available on this Django's SimpleTestCase in
            # all versions -- assert on the record list directly instead.
            import logging
            records = []
            handler = logging.Handler()
            handler.emit = records.append
            logger = logging.getLogger(_MODULE)
            logger.addHandler(handler)
            try:
                _import_production({})
            finally:
                logger.removeHandler(handler)
        self.assertEqual(records, [])

    def test_no_hardcoded_real_address_fallback(self):
        settings_mod = _import_production({})
        self.assertEqual(settings_mod.DEFAULT_FROM_EMAIL, "")
        self.assertEqual(settings_mod.SERVER_EMAIL, "")
        self.assertEqual(settings_mod.MODERATION_EMAIL, "")
        self.assertEqual(settings_mod.CONTACT_EMAIL, "")

    def test_moderation_and_contact_fall_back_to_default_from(self):
        settings_mod = _import_production({"DEFAULT_FROM_EMAIL": "hello@example.com"})
        self.assertEqual(settings_mod.MODERATION_EMAIL, "hello@example.com")
        self.assertEqual(settings_mod.CONTACT_EMAIL, "hello@example.com")

    def test_explicit_moderation_and_contact_override_default_from(self):
        settings_mod = _import_production({
            "DEFAULT_FROM_EMAIL": "hello@example.com",
            "MODERATION_EMAIL": "mod@example.com",
            "CONTACT_EMAIL": "contact@example.com",
        })
        self.assertEqual(settings_mod.MODERATION_EMAIL, "mod@example.com")
        self.assertEqual(settings_mod.CONTACT_EMAIL, "contact@example.com")

    def test_account_email_verification_stays_mandatory(self):
        settings_mod = _import_production({})
        self.assertEqual(settings_mod.ACCOUNT_EMAIL_VERIFICATION, "mandatory")
