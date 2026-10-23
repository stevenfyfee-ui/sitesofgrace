"""
Tests for the Contact page form (home.ContactPage.serve), the
ContactMessage model, the staff alert, Turnstile, and the admin inbox.

Every name and address here is fictitious. No real email is sent
(locmem backend) and Cloudflare is never called (urlopen is mocked).
"""
import io
import json
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Page, PageViewRestriction, Site

from catalog.models import SacredSitePage, SaintPage
from contact import forms as contact_forms
from contact.models import (
    IP_HASH_RETENTION_DAYS,
    MESSAGE_RETENTION_DAYS,
    PRAYER_RETENTION_DAYS,
    SPAM_RETENTION_DAYS,
    ContactMessage,
)
from home.models import ContactPage, HomePage, StandardPage

REMOTE_ADDR = "203.0.113.77"
SENDER = {"name": "John Doe", "email": "john.doe@example.com"}

MAIL = override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CONTACT_EMAIL="inbox@example.com",
    SUPPORT_EMAIL="",
    MODERATION_EMAIL="moderation@example.com",
    DEFAULT_FROM_EMAIL="no-reply@example.com",
    TURNSTILE_SITE_KEY="",
    TURNSTILE_SECRET_KEY="",
)


def aged_ts(seconds=60):
    """A form token issued `seconds` ago."""
    with mock.patch("django.core.signing.time.time", return_value=time.time() - seconds):
        return contact_forms.issue_ts()


@MAIL
class ContactTestCase(TestCase):
    def setUp(self):
        # The flood guard lives in the cache; don't let one test's hits count
        # against the next.
        cache.clear()
        self.root = Page.get_first_root_node()
        Site.objects.update(is_default_site=False)
        Site.objects.create(hostname="testserver", root_page=self.root, is_default_site=True)
        self.homepage = HomePage(title="Home", slug="home-test")
        self.root.add_child(instance=self.homepage)
        self.page = ContactPage(title="Contact")
        self.homepage.add_child(instance=self.page)
        self.site_page = SacredSitePage(title="Our Lady of Example", slug="our-lady-of-example",
                                        category="Shrine & Basilica")
        self.homepage.add_child(instance=self.site_page)

    def tearDown(self):
        cache.clear()

    def data(self, **overrides):
        data = {
            **SENDER,
            "topic": "question",
            "message": "When is the shrine open?",
            "related_page": "",
            "website": "",
            "ts": aged_ts(),
        }
        data.update(overrides)
        return data

    def post(self, **overrides):
        return self.client.post(self.page.url, self.data(**overrides), REMOTE_ADDR=REMOTE_ADDR)


class SubmitTests(ContactTestCase):
    def test_valid_post_saves_redirects_and_thanks_once(self):
        response = self.post()
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response["Location"].endswith("?sent=1#contact-form"))
        message = ContactMessage.objects.get()
        self.assertEqual(message.status, ContactMessage.STATUS_NEW)
        self.assertEqual(message.name, "John Doe")
        self.assertEqual(message.topic, "question")

        thanks = self.client.get(self.page.url + "?sent=1")
        self.assertEqual(thanks.content.decode().count("Thank You, John"), 1)
        self.assertEqual(thanks["Cache-Control"], "private, no-store")
        # Popped after one render; the name never rides in the URL.
        again = self.client.get(self.page.url + "?sent=1")
        self.assertNotContains(again, "Thank You, John")
        self.assertContains(again, "Thank You")

    def test_prayer_thank_you_wording(self):
        self.post(topic="prayer", message="For my family.")
        thanks = self.client.get(self.page.url + "?sent=1")
        self.assertContains(thanks, "we will remember it in prayer")

    def test_signed_in_sender_is_linked(self):
        user = get_user_model().objects.create_user("johndoe", "john.doe@example.com", "pw-12345-x")
        self.client.force_login(user)
        self.post()
        self.assertEqual(ContactMessage.objects.get().user, user)

    def test_csrf_is_enforced(self):
        from django.test import Client

        response = Client(enforce_csrf_checks=True).post(self.page.url, self.data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ContactMessage.objects.exists())

    def test_invalid_post_shows_errors_and_summary(self):
        response = self.post(name="", email="not-an-email", message="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())
        self.assertContains(response, "data-contact-errors")
        self.assertContains(response, 'href="#id_name"')
        self.assertContains(response, "Please tell us your name.")
        self.assertContains(response, "We&#x27;ll need a valid email address to reply.")
        self.assertContains(response, 'aria-invalid="true" aria-describedby="messageError"')

    def test_raw_ip_is_never_stored(self):
        self.post()
        self.post(website="https://spam.example")
        for row in ContactMessage.objects.values():
            for value in row.values():
                self.assertNotIn(REMOTE_ADDR, str(value))


class SpamTests(ContactTestCase):
    def assert_spam(self, response):
        self.assertEqual(response.status_code, 303)
        message = ContactMessage.objects.get()
        self.assertEqual(message.status, ContactMessage.STATUS_SPAM)
        self.assertEqual(mail.outbox, [])
        # The bot sees the normal thank-you.
        self.assertContains(self.client.get(self.page.url + "?sent=1"), "Thank You, John")

    def test_honeypot(self):
        self.assert_spam(self.post(website="https://example.com"))

    def test_missing_or_tampered_ts(self):
        self.assert_spam(self.post(ts=""))

    def test_tampered_ts(self):
        self.assert_spam(self.post(ts=aged_ts() + "x"))

    def test_too_fast(self):
        self.assert_spam(self.post(ts=aged_ts(seconds=1)))

    def test_too_old(self):
        self.assert_spam(self.post(ts=aged_ts(seconds=25 * 60 * 60)))

    def test_four_urls(self):
        links = " ".join(f"https://example.com/{n}" for n in range(4))
        self.assert_spam(self.post(message=f"Look: {links}"))

    def test_three_urls_is_fine(self):
        links = " ".join(f"https://example.com/{n}" for n in range(3))
        self.post(message=f"Sources: {links}")
        self.assertEqual(ContactMessage.objects.get().status, ContactMessage.STATUS_NEW)


class RateLimitTests(ContactTestCase):
    def test_sixth_message_in_an_hour_is_refused(self):
        for _ in range(5):
            self.assertEqual(self.post().status_code, 303)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You&#x27;ve sent several messages in a short time.")
        self.assertEqual(ContactMessage.objects.count(), 5)

    def test_older_messages_dont_count(self):
        for _ in range(5):
            self.post()
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.post().status_code, 303)
        self.assertEqual(ContactMessage.objects.count(), 6)

    def test_spam_doesnt_count(self):
        for _ in range(5):
            self.post(website="x")
        self.assertEqual(self.post().status_code, 303)
        self.assertEqual(ContactMessage.objects.filter(status="new").count(), 1)


class RelatedPageTests(ContactTestCase):
    def related(self, page):
        self.post(related_page=str(page.pk))
        return ContactMessage.objects.latest("created_at").related_page

    def test_live_public_site_is_accepted(self):
        self.assertEqual(self.related(self.site_page), self.site_page.page_ptr)

    def test_live_saint_is_accepted(self):
        saint = SaintPage(title="Saint Example", slug="saint-example")
        self.homepage.add_child(instance=saint)
        self.assertEqual(self.related(saint).pk, saint.pk)

    def test_unpublished_saint_is_dropped(self):
        saint = SaintPage(title="Saint Draft", slug="saint-draft", live=False)
        self.homepage.add_child(instance=saint)
        self.assertIsNone(self.related(saint))

    def test_restricted_page_is_dropped(self):
        PageViewRestriction.objects.create(
            page=self.site_page, restriction_type=PageViewRestriction.PASSWORD, password="x",
        )
        self.assertIsNone(self.related(self.site_page))

    def test_standard_page_is_dropped(self):
        other = StandardPage(title="Explore", slug="explore-test")
        self.homepage.add_child(instance=other)
        self.assertIsNone(self.related(other))

    def test_garbage_is_dropped(self):
        self.post(related_page="'; drop table--")
        self.assertIsNone(ContactMessage.objects.get().related_page)


class PrefillTests(ContactTestCase):
    def test_topic_and_page_are_preselected(self):
        response = self.client.get(f"{self.page.url}?topic=correction&page={self.site_page.pk}")
        self.assertContains(response, '<option value="correction" selected>')
        self.assertContains(response, f'name="related_page" value="{self.site_page.pk}"')
        self.assertContains(response, "Our Lady of Example")
        self.assertContains(response, "What&#x27;s not right?")

    def test_unknown_topic_is_ignored(self):
        response = self.client.get(f"{self.page.url}?topic=bogus")
        self.assertContains(response, '<option value="question" selected>')
        self.assertNotContains(response, "bogus")

    def test_bad_page_is_ignored(self):
        draft = SaintPage(title="Saint Hidden", slug="saint-hidden", live=False)
        self.homepage.add_child(instance=draft)
        response = self.client.get(f"{self.page.url}?page={draft.pk}")
        self.assertNotContains(response, "Saint Hidden")
        self.assertContains(response, 'name="related_page" value=""')

    def test_signed_in_user_is_prefilled(self):
        user = get_user_model().objects.create_user(
            "johndoe", "john.doe@example.com", "pw-12345-x", first_name="John", last_name="Doe",
        )
        self.client.force_login(user)
        response = self.client.get(self.page.url)
        self.assertContains(response, 'value="John Doe"')
        self.assertContains(response, 'value="john.doe@example.com"')


class CorrectionUrlTests(ContactTestCase):
    def render(self, page):
        return Template("{% load contact_tags %}{% correction_url page %}").render(Context({"page": page}))

    def test_points_at_the_live_contact_page(self):
        self.assertEqual(
            self.render(self.site_page),
            f"{self.page.url}?topic=correction&amp;page={self.site_page.pk}",
        )

    def test_empty_without_a_live_contact_page(self):
        self.page.unpublish()
        self.assertEqual(self.render(self.site_page), "")

    def test_site_page_shows_the_link(self):
        response = self.client.get(self.site_page.url)
        self.assertContains(response, "Spot an error?")
        self.assertContains(response, f"?topic=correction&amp;page={self.site_page.pk}")

    def test_saint_page_shows_the_link(self):
        saint = SaintPage(title="Saint Example", slug="saint-example")
        self.homepage.add_child(instance=saint)
        self.assertContains(self.client.get(saint.url), f"?topic=correction&amp;page={saint.pk}")


class AlertTests(ContactTestCase):
    def test_one_alert_to_staff_with_reply_to_sender(self):
        self.post(related_page=str(self.site_page.pk))
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["inbox@example.com"])
        self.assertEqual(email.reply_to, ["john.doe@example.com"])
        self.assertEqual(email.from_email, "no-reply@example.com")
        self.assertNotIn("john.doe@example.com", email.to + email.cc + email.bcc)
        self.assertEqual(email.subject, "[Sites of Grace] Ask a question: John Doe")
        message = ContactMessage.objects.get()
        self.assertIn("When is the shrine open?", email.body)
        self.assertIn("Our Lady of Example", email.body)
        self.assertIn(reverse("contact_messages:edit", args=[message.pk]), email.body)

    def test_header_injection_is_stripped(self):
        self.post(name="John\r\nBcc: victim@example.com")
        email = mail.outbox[0]
        self.assertNotIn("\r", email.subject)
        self.assertNotIn("\n", email.subject)
        self.assertEqual(email.bcc, [])
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("victim@example.com", email.message()["To"] or "")
        self.assertIsNone(email.message()["Bcc"])

    def test_prayer_alert_leaves_out_the_message(self):
        self.post(topic="prayer", message="Please pray for my sister's surgery.")
        body = mail.outbox[0].body
        self.assertNotIn("sister", body)
        self.assertNotIn("Please pray for my sister's surgery.", body)
        message = ContactMessage.objects.get()
        self.assertIn("Prayer request", mail.outbox[0].subject)
        self.assertIn("John Doe", body)
        self.assertIn("john.doe@example.com", body)
        self.assertIn(reverse("contact_messages:edit", args=[message.pk]), body)
        # Saved in full for the admin.
        self.assertEqual(message.message, "Please pray for my sister's surgery.")

    @override_settings(SUPPORT_EMAIL="support@example.com")
    def test_billing_goes_to_support(self):
        self.post(topic="billing")
        self.assertEqual(mail.outbox[0].to, ["support@example.com"])
        self.post(topic="question")
        self.assertEqual(mail.outbox[1].to, ["inbox@example.com"])

    @override_settings(CONTACT_EMAIL="")
    def test_falls_back_to_moderation_email(self):
        self.post()
        self.assertEqual(mail.outbox[0].to, ["moderation@example.com"])

    @override_settings(CONTACT_EMAIL="", MODERATION_EMAIL="", ADMINS=[("Admin", "admin@example.com")])
    def test_falls_back_to_admins(self):
        self.post()
        self.assertEqual(mail.outbox[0].to, ["admin@example.com"])

    def test_backend_failure_still_saves_and_thanks(self):
        with mock.patch("contact.notify.EmailMessage.send", side_effect=OSError("smtp down")), \
                self.assertLogs("contact.notify", "ERROR"):
            response = self.post()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertContains(self.client.get(self.page.url + "?sent=1"), "Thank You, John")

    @override_settings(CONTACT_EMAIL="", MODERATION_EMAIL="", ADMINS=[])
    def test_no_recipient_logs_a_warning(self):
        with self.assertLogs("contact.notify", "WARNING") as logs:
            response = self.post()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn("no alert was sent", logs.output[0])


class TurnstileTests(ContactTestCase):
    def test_off_by_default(self):
        with mock.patch("contact.turnstile.urllib.request.urlopen") as urlopen:
            response = self.client.get(self.page.url)
            self.post()
        self.assertNotContains(response, "cf-turnstile")
        self.assertNotContains(response, "challenges.cloudflare.com")
        urlopen.assert_not_called()
        self.assertEqual(ContactMessage.objects.count(), 1)

    @override_settings(TURNSTILE_SITE_KEY="site-key-test", TURNSTILE_SECRET_KEY="secret-test")
    def test_failed_verification_blocks_the_save(self):
        self.assertContains(self.client.get(self.page.url), 'data-sitekey="site-key-test"')
        reply = io.BytesIO(json.dumps({"success": False}).encode())
        with mock.patch("contact.turnstile.urllib.request.urlopen", return_value=reply) as urlopen:
            response = self.post(**{"cf-turnstile-response": "token"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "We couldn&#x27;t confirm you&#x27;re not a robot.")
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)

    @override_settings(TURNSTILE_SITE_KEY="site-key-test", TURNSTILE_SECRET_KEY="secret-test")
    def test_passed_verification_saves(self):
        reply = io.BytesIO(json.dumps({"success": True}).encode())
        with mock.patch("contact.turnstile.urllib.request.urlopen", return_value=reply):
            self.assertEqual(self.post(**{"cf-turnstile-response": "token"}).status_code, 303)
        self.assertEqual(ContactMessage.objects.count(), 1)


class RetentionTests(TestCase):
    def make(self, topic, age, ip_hash="a" * 64, status="new"):
        message = ContactMessage.objects.create(
            topic=topic, name="John Doe", email="john.doe@example.com", message="Hello", ip_hash=ip_hash,
            status=status,
        )
        ContactMessage.objects.filter(pk=message.pk).update(created_at=self.now - age)
        return message.pk

    def setUp(self):
        self.now = timezone.now()

    def test_prayer_window_edges(self):
        minute = timedelta(minutes=1)
        kept = self.make("prayer", timedelta(days=PRAYER_RETENTION_DAYS) - minute)
        gone = self.make("prayer", timedelta(days=PRAYER_RETENTION_DAYS) + minute)
        # Another topic at the same age stays.
        other = self.make("question", timedelta(days=PRAYER_RETENTION_DAYS) + minute)
        ContactMessage.purge_expired(now=self.now)
        remaining = set(ContactMessage.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {kept, other})
        self.assertNotIn(gone, remaining)

    def test_message_window_edges(self):
        minute = timedelta(minutes=1)
        kept = self.make("question", timedelta(days=MESSAGE_RETENTION_DAYS) - minute)
        gone = self.make("question", timedelta(days=MESSAGE_RETENTION_DAYS) + minute)
        spam = self.make("other", timedelta(days=MESSAGE_RETENTION_DAYS) + minute)
        ContactMessage.purge_expired(now=self.now)
        remaining = set(ContactMessage.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {kept})
        self.assertFalse({gone, spam} & remaining)

    def test_spam_window_edges(self):
        minute = timedelta(minutes=1)
        kept = self.make("question", timedelta(days=SPAM_RETENTION_DAYS) - minute, status="spam")
        gone = self.make("question", timedelta(days=SPAM_RETENTION_DAYS) + minute, status="spam")
        # A real message at the same age stays.
        real = self.make("question", timedelta(days=SPAM_RETENTION_DAYS) + minute)
        ContactMessage.purge_expired(now=self.now)
        remaining = set(ContactMessage.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {kept, real})
        self.assertNotIn(gone, remaining)

    def test_ip_hash_is_blanked_after_seven_days(self):
        minute = timedelta(minutes=1)
        fresh = self.make("question", timedelta(days=IP_HASH_RETENTION_DAYS) - minute)
        old = self.make("question", timedelta(days=IP_HASH_RETENTION_DAYS) + minute)
        ContactMessage.purge_expired(now=self.now)
        self.assertEqual(ContactMessage.objects.get(pk=fresh).ip_hash, "a" * 64)
        self.assertEqual(ContactMessage.objects.get(pk=old).ip_hash, "")

    def test_management_command(self):
        from django.core.management import call_command

        self.make("prayer", timedelta(days=PRAYER_RETENTION_DAYS + 1))
        out = io.StringIO()
        call_command("purge_contact_messages", stdout=out)
        self.assertIn("Deleted 1 message(s)", out.getvalue())
        self.assertFalse(ContactMessage.objects.exists())


class InboxTests(TestCase):
    def setUp(self):
        self.message = ContactMessage.objects.create(
            topic="question", name="John Doe", email="john.doe@example.com", message="Hello",
        )
        ContactMessage.objects.create(
            topic="other", name="Spam Bot", email="bot@example.com", message="Buy", status="spam",
        )
        User = get_user_model()
        self.editor = User.objects.create_user("editor", "editor@example.com", "pw-12345-x", is_staff=True)
        self.editor.user_permissions.add(Permission.objects.get(codename="access_admin"))
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw-12345-x")

    def test_non_superuser_staff_are_refused(self):
        # Wagtail's admin turns PermissionDenied into a redirect to the
        # dashboard with "Sorry, you do not have permission..." for a normal
        # request, and a plain 403 for XHR. Either way, nothing is shown.
        self.client.force_login(self.editor)
        for url in (
            reverse("contact_messages:index"),
            reverse("contact_messages:edit", args=[self.message.pk]),
        ):
            response = self.client.get(url)
            self.assertRedirects(response, reverse("wagtailadmin_home"), fetch_redirect_response=False)
            self.assertNotContains(response, "john.doe@example.com", status_code=302)
            xhr = self.client.get(url, headers={"x-requested-with": "XMLHttpRequest"})
            self.assertEqual(xhr.status_code, 403, url)

    def test_menu_item_hidden_from_non_superusers(self):
        self.client.force_login(self.editor)
        self.assertNotContains(self.client.get(reverse("wagtailadmin_home")), "contact_messages")

    def test_superuser_list_hides_spam_unless_filtered(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("contact_messages:index"))
        self.assertContains(response, "John Doe")
        self.assertNotContains(response, "Spam Bot")
        spam = self.client.get(reverse("contact_messages:index") + "?status=spam")
        self.assertContains(spam, "Spam Bot")
        self.assertContains(response, reverse("contact_messages:edit", args=[self.message.pk]))

    def test_menu_label_counts_new_messages(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("wagtailadmin_home")), "Messages (1)")

    def test_edit_changes_only_status_and_note(self):
        self.client.force_login(self.admin)
        url = reverse("contact_messages:edit", args=[self.message.pk])
        page = self.client.get(url)
        self.assertContains(page, "mailto:john.doe@example.com?subject=")
        self.client.post(url, {
            "status": "replied", "staff_note": "Answered.",
            "name": "Changed", "email": "changed@example.com", "message": "Changed",
        })
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, "replied")
        self.assertEqual(self.message.staff_note, "Answered.")
        self.assertEqual(self.message.name, "John Doe")
        self.assertEqual(self.message.message, "Hello")

    def test_superusers_cannot_add_messages(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("contact_messages:add"), headers={"x-requested-with": "XMLHttpRequest"})
        self.assertEqual(response.status_code, 403)
