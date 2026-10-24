"""apply_content_fixes_2026_10: the October 2026 one-off content fixes.

Protects: the dry run writes nothing; fields change only from the expected
old value, once, as one revision by the chosen user; a draft or an
unexpected value skips the page; the duplicate page is unpublished with a
permanent redirect only when nothing points to it; Akita's draft is
published or reverted on request; --verify fails until every fix is in.
"""
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.contrib.redirects.models import Redirect

from catalog.management.commands import apply_content_fixes_2026_10 as fixes
from catalog.models import SacredSitePage
from catalog.tests_v2_site import V2SiteTestCase
from pilgrims.models import SiteVisit

OLD_LINK, NEW_LINK = "https://old.example.com/", "https://new.example.com/"


class ContentFixesTests(V2SiteTestCase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser("fixer", "fixer@example.com", "x")
        self.linked = self.make_site("fix-link", title="Link Site (sample)", location_link=OLD_LINK)
        self.moved = self.make_site("fix-move", title="Moved Site (sample)",
                                    latitude=Decimal("43.190800"), longitude=Decimal("17.678900"))
        self.dup = self.make_site("fix-dup", title="Duplicate (sample)")
        self.keep = self.make_site("fix-keep", title="Keeper (sample)")
        self.akita = self.make_site("fix-draft", title="Draft Site (sample)", summary_short="Live text.")
        patches = [
            mock.patch.object(fixes, "FIELD_FIXES", [
                (self.linked.pk, self.linked.title, {"location_link": (OLD_LINK, NEW_LINK)}),
                (self.moved.pk, self.moved.title, {"latitude": (Decimal("43.190800"), Decimal("43.190560")),
                                                   "longitude": (Decimal("17.678900"), Decimal("17.677500"))}),
            ]),
            mock.patch.object(fixes, "DUPLICATE", (self.dup.pk, self.dup.title)),
            mock.patch.object(fixes, "DUPLICATE_OF", (self.keep.pk, self.keep.title)),
            mock.patch.object(fixes, "AKITA", (self.akita.pk, self.akita.title)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_cmd(self, *args):
        out = StringIO()
        call_command("apply_content_fixes_2026_10", *args, "--user", "fixer", stdout=out)
        return out.getvalue()

    def fresh(self, page):
        return SacredSitePage.objects.get(pk=page.pk)

    def test_dry_run_writes_nothing(self):
        out = self.run_cmd("--dry-run")
        self.assertIn("Would change: 3", out)
        self.assertEqual(self.fresh(self.linked).location_link, OLD_LINK)
        self.assertTrue(self.fresh(self.dup).live)
        self.assertFalse(Redirect.objects.exists())
        self.assertEqual(self.fresh(self.linked).revisions.count(), 0)

    def test_applies_once_as_one_revision_by_the_user_then_verifies(self):
        with self.assertRaises(CommandError):
            call_command("apply_content_fixes_2026_10", "--verify", stdout=StringIO())
        self.assertIn("Changed: 3", self.run_cmd())
        linked = self.fresh(self.linked)
        self.assertEqual(linked.location_link, NEW_LINK)
        self.assertEqual(linked.revisions.count(), 1)
        self.assertEqual(linked.live_revision.user, self.admin)
        moved = self.fresh(self.moved)
        self.assertEqual((moved.latitude, moved.longitude), (Decimal("43.190560"), Decimal("17.677500")))
        self.assertFalse(self.fresh(self.dup).live)
        redirect = Redirect.objects.get()
        self.assertEqual((redirect.redirect_page_id, redirect.is_permanent, redirect.site_id), (self.keep.pk, True, None))
        response = self.client.get(self.dup.url)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], self.keep.url)
        out = self.run_cmd()
        self.assertIn("Changed: 0", out)
        self.assertIn("Already correct: 3", out)
        self.assertEqual(self.fresh(self.linked).revisions.count(), 1)
        call_command("apply_content_fixes_2026_10", "--verify", stdout=StringIO())

    def test_unexpected_value_and_draft_are_skipped(self):
        SacredSitePage.objects.filter(pk=self.linked.pk).update(location_link="https://someone-else.example.com/")
        moved = self.fresh(self.moved)
        moved.summary_short = "Editor's draft."
        moved.save_revision()
        out = self.run_cmd()
        self.assertIn("conflict", out)
        self.assertIn("unpublished changes", out)
        self.assertEqual(self.fresh(self.linked).location_link, "https://someone-else.example.com/")
        self.assertEqual(self.fresh(self.moved).latitude, Decimal("43.190800"))

    def test_duplicate_with_a_reference_is_left_alone(self):
        SiteVisit.objects.create(owner=self.admin, site=self.dup, status="visited")
        out = self.run_cmd()
        self.assertIn("still referenced", out)
        self.assertTrue(self.fresh(self.dup).live)
        self.assertFalse(Redirect.objects.exists())

    def test_duplicate_linked_from_another_page_is_left_alone(self):
        SacredSitePage.objects.filter(pk=self.keep.pk).update(
            the_story=f'<p>See <a linktype="page" id="{self.dup.pk}">the other page</a>.</p>')
        self.assertIn("still referenced", self.run_cmd())
        self.assertTrue(self.fresh(self.dup).live)

    def test_akita_revert_drops_the_draft_and_publish_publishes_it(self):
        page = self.fresh(self.akita)
        page.summary_short = "Draft text."
        page.save_revision()
        self.run_cmd("--akita", "revert", "--dry-run")
        self.assertTrue(self.fresh(self.akita).has_unpublished_changes)
        self.run_cmd("--akita", "revert")
        page = self.fresh(self.akita)
        self.assertFalse(page.has_unpublished_changes)
        self.assertEqual(page.summary_short, "Live text.")
        self.assertEqual(page.live_revision.user, self.admin)
        page.summary_short = "Second draft."
        page.save_revision()
        self.run_cmd("--akita", "publish")
        page = self.fresh(self.akita)
        self.assertFalse(page.has_unpublished_changes)
        self.assertEqual(page.summary_short, "Second draft.")
        self.assertIn("no pending draft", self.run_cmd("--akita", "publish"))
