"""The go-live commands that replace admin clicking in docs/v2/GO-LIVE.md.

swap_contact_page, publish_legal_pages, set_legal_details (home) and
publish_hubs (destinations): each is idempotent, has a --dry-run that
changes nothing, and refuses rather than half-doing a job.
"""
import datetime
import types
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from destinations.models import DestinationHubPage, DestinationIndexPage
from home import legal
from home.management.commands import publish_legal_pages
from home.models import ContactPage, HomePage, LegalDetails, LegalPage, StandardPage

DETAILS = {
    "operator_name": "Example Ministry (sample)",
    "contact_email": "hello@example.com",
    "mailing_address": "123 Main St, Anytown",
    "dmca_agent_name": "John Doe (sample)",
    "dmca_agent_address": "123 Main St, Anytown",
    "dmca_agent_phone": "555-0100",
    "dmca_agent_email": "dmca@example.com",
}


class GoLiveTestCase(WagtailPageTestCase):
    def setUp(self):
        Site.clear_site_root_paths_cache()
        root = Page.get_first_root_node()
        self.home = HomePage(title="Home", slug="golive-home")
        root.add_child(instance=self.home)
        Site.objects.filter(is_default_site=True).update(root_page=self.home)
        # .update() skips the signal that clears Wagtail's cached site root
        # paths, so clear it now and again afterwards -- otherwise the next
        # app's tests see this test's (rolled-back) home page.
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)

    def run_cmd(self, *args, **kwargs):
        out = StringIO()
        call_command(*args, stdout=out, **kwargs)
        return out.getvalue()


class SwapContactPageTests(GoLiveTestCase):
    def test_swaps_the_standard_page_for_a_contact_page_once(self):
        old = StandardPage(title="Contact", slug="contact")
        self.home.add_child(instance=old)
        out = self.run_cmd("swap_contact_page", "--dry-run")
        self.assertIn("Would unpublish the StandardPage", out)
        self.assertFalse(ContactPage.objects.exists())
        self.assertTrue(StandardPage.objects.get(pk=old.pk).live)

        self.run_cmd("swap_contact_page")
        old = StandardPage.objects.get(pk=old.pk)
        self.assertEqual((old.slug, old.live), ("contact-old", False))
        self.assertEqual(old.get_latest_revision_as_object().slug, "contact-old")
        contact = ContactPage.objects.live().get()
        self.assertEqual(contact.url_path, self.home.url_path + "contact/")
        self.assertEqual(self.client.get("/contact/").status_code, 200)

        out = self.run_cmd("swap_contact_page")
        self.assertIn("Nothing to do", out)
        self.assertEqual(ContactPage.objects.count(), 1)

    def test_creates_a_contact_page_when_there_is_none(self):
        self.run_cmd("swap_contact_page")
        self.assertTrue(ContactPage.objects.live().filter(slug="contact").exists())

    def test_refuses_an_unexpected_page_type(self):
        self.home.add_child(instance=Page(title="Contact", slug="contact"))
        with self.assertRaises(CommandError):
            self.run_cmd("swap_contact_page")
        self.assertFalse(ContactPage.objects.exists())


class LegalCommandsTests(GoLiveTestCase):
    def setUp(self):
        super().setUp()
        self.run_cmd("create_legal_pages")

    def fill(self, **values):
        details = LegalDetails.load()
        for name, value in values.items():
            setattr(details, name, value)
        details.save()

    def test_refuses_and_publishes_nothing_while_a_value_is_blank(self):
        self.fill(**{k: v for k, v in DETAILS.items() if not k.startswith("dmca")})
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("publish_legal_pages", stdout=out)
        self.assertIn("copyright-policy", out.getvalue())
        self.assertIn("DMCA agent name", out.getvalue())
        self.assertEqual(LegalPage.objects.live().count(), 0, "all or none")

    def test_dry_run_then_publishes_all_ten_once(self):
        self.fill(**DETAILS)
        out = self.run_cmd("publish_legal_pages", "--dry-run")
        self.assertIn("Would publish", out)
        self.assertEqual(LegalPage.objects.live().count(), 0)
        self.run_cmd("publish_legal_pages")
        self.assertEqual(LegalPage.objects.live().count(), len(legal.LEGAL_SLUGS))
        out = self.run_cmd("publish_legal_pages")
        self.assertIn("Publishing: none", out)

    def test_effective_dry_run_shows_old_and_new_dates_and_changes_nothing(self):
        self.fill(**DETAILS)
        old = {p.slug: p.get_latest_revision_as_object().effective_date for p in LegalPage.objects.all()}
        out = self.run_cmd("publish_legal_pages", "--effective", "2026-11-20", "--dry-run")
        for slug in legal.LEGAL_SLUGS:
            self.assertIn(f"{slug}: {old[slug]} -> 2026-11-20", out)
        self.assertEqual(LegalPage.objects.live().count(), 0)
        for page in LegalPage.objects.all():
            self.assertEqual(page.get_latest_revision_as_object().effective_date, old[page.slug])

    def test_effective_sets_the_date_on_all_ten_as_they_publish(self):
        self.fill(**DETAILS)
        self.run_cmd("publish_legal_pages", "--effective", "2026-11-20")
        pages = LegalPage.objects.live()
        self.assertEqual(pages.count(), len(legal.LEGAL_SLUGS))
        for page in pages:
            self.assertEqual(page.effective_date, datetime.date(2026, 11, 20))
            self.assertFalse(page.has_unpublished_changes)

    def test_effective_without_a_date_is_today_in_los_angeles(self):
        # 05:00 UTC on Nov 7 is still Nov 6 in Los Angeles.
        utc_now = datetime.datetime(2026, 11, 7, 5, 0, tzinfo=datetime.timezone.utc)
        fake = types.SimpleNamespace(
            date=datetime.date,
            datetime=types.SimpleNamespace(now=lambda tz: utc_now.astimezone(tz)),
        )
        self.fill(**DETAILS)
        with mock.patch.object(publish_legal_pages, "datetime", fake):
            out = self.run_cmd("publish_legal_pages", "--effective", "--dry-run")
        self.assertIn("set to 2026-11-06", out)

    def test_effective_refuses_when_a_page_is_already_live(self):
        self.fill(**DETAILS)
        page = LegalPage.objects.get(slug="cookie-notice")
        page.get_latest_revision_as_object().save_revision().publish()
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("publish_legal_pages", "--effective", "2026-11-20", stdout=out)
        self.assertIn("cookie-notice: already live", out.getvalue())
        self.assertEqual(LegalPage.objects.live().count(), 1, "all or none")

    def test_effective_rejects_a_bad_date(self):
        with self.assertRaises(CommandError):
            self.run_cmd("publish_legal_pages", "--effective", "20-11-2026")
        self.assertEqual(LegalPage.objects.live().count(), 0)

    def test_set_legal_details_reads_the_prompt_and_never_echoes_values(self):
        answers = iter([DETAILS[name] for name in legal.TOKENS.values()])
        out = self.run_cmd("set_legal_details", _input=lambda prompt: next(answers))
        details = LegalDetails.load()
        for name, value in DETAILS.items():
            self.assertEqual(getattr(details, name), value)
        for value in DETAILS.values():
            self.assertNotIn(value, out)
        self.assertIn("Still blank: none", out)

    def test_set_legal_details_keeps_values_on_enter_and_dry_run_saves_nothing(self):
        self.fill(operator_name="Kept (sample)")
        out = self.run_cmd("set_legal_details", "--dry-run", _input=lambda prompt: "")
        self.assertIn("would update: nothing", out)
        self.assertEqual(LegalDetails.load().operator_name, "Kept (sample)")
        answers = iter(["", "not-an-email"] + [""] * 5)
        with self.assertRaises(CommandError):
            self.run_cmd("set_legal_details", _input=lambda prompt: next(answers))
        self.assertEqual(LegalDetails.load().contact_email, "")

    def test_set_legal_details_refuses_without_a_prompt(self):
        with self.assertRaises(CommandError):
            self.run_cmd("set_legal_details")


class PublishHubsTests(GoLiveTestCase):
    def setUp(self):
        super().setUp()
        self.run_cmd("create_destination_hubs")

    def give_intro(self, slug, text="Intro."):
        hub = DestinationHubPage.objects.get(slug=slug)
        draft = hub.get_latest_revision_as_object()
        draft.intro = text
        draft.save_revision()

    def test_publishes_hubs_with_an_intro_and_lists_the_rest(self):
        self.give_intro("assisi-umbria")
        out = self.run_cmd("publish_hubs", "--dry-run")
        self.assertIn("Would publish: Assisi & Umbria", out)
        self.assertIn("Skipped (no intro yet): Rome & Vatican City, Paris & Northern France, Portugal", out)
        self.assertFalse(DestinationHubPage.objects.live().exists())
        self.run_cmd("publish_hubs")
        self.assertEqual(list(DestinationHubPage.objects.live().values_list("slug", flat=True)), ["assisi-umbria"])
        self.assertTrue(DestinationIndexPage.objects.get().live)
        self.assertEqual(DestinationHubPage.objects.get(slug="assisi-umbria").intro, "Intro.")
        self.assertIn("Already live: Assisi & Umbria", self.run_cmd("publish_hubs"))

    def test_slug_filter(self):
        self.give_intro("assisi-umbria")
        self.give_intro("portugal")
        self.run_cmd("publish_hubs", "--slug", "portugal")
        self.assertEqual(list(DestinationHubPage.objects.live().values_list("slug", flat=True)), ["portugal"])
        with self.assertRaises(CommandError):
            self.run_cmd("publish_hubs", "--slug", "nowhere")
