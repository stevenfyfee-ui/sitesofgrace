"""apply_summaries: replace summary_short on live site/trail pages from a JSON file.

What these protect: a dry run writes nothing; --commit sets summary_short only and
publishes it as one logged revision per page; an ambiguous or missing title, a
url_path_hint that doesn't match, text over 200 characters and a page with a waiting
draft are all reported and skipped, never guessed or published by accident.
"""
import json
import os
import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from wagtail.models import PageLogEntry, Site

from catalog.models import PilgrimageTrailPage, SacredSitePage
from catalog.tests import SacredSitePageTestCase
from home.models import StandardPage

LONG = "A long summary that goes on. " * 20


class ApplySummariesTestCase(SacredSitePageTestCase):
    def setUp(self):
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.marian = StandardPage(title="Marian Apparitions", slug="marian-apparitions", layout="category_directory")
        self.routes = StandardPage(title="Pilgrimage Routes", slug="pilgrimage-routes", layout="category_directory")
        self.site_root().add_child(instance=self.marian)
        self.site_root().add_child(instance=self.routes)

    def site(self, title, slug, parent=None, **fields):
        page = SacredSitePage(title=title, slug=slug, category="Marian Apparition",
                              summary_short=fields.pop("summary_short", LONG), **fields)
        (parent or self.marian).add_child(instance=page)
        page.save_revision().publish()
        return SacredSitePage.objects.get(pk=page.pk)

    def run_cmd(self, entries, *flags):
        path = os.path.join(self.tmp, "summaries.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"pages": entries}, fh, ensure_ascii=False)
        out = StringIO()
        call_command("apply_summaries", path, *flags, stdout=out)
        return out.getvalue()


class DryRunTests(ApplySummariesTestCase):
    def test_a_dry_run_reports_and_changes_nothing(self):
        page = self.site("Our Lady of Somewhere", "somewhere")
        revisions = page.revisions.count()
        out = self.run_cmd([{"title": "Our Lady of Somewhere", "summary_short": "Short and sweet."}])
        self.assertIn(f"[1] Would change #{page.pk} 'Our Lady of Somewhere'", out)
        self.assertIn(f"{len(LONG)} -> 16 chars", out)
        self.assertIn("new: Short and sweet.", out)
        self.assertIn("Would change: 1; unchanged 0; skipped 0.", out)
        page.refresh_from_db()
        self.assertEqual(page.summary_short, LONG)
        self.assertEqual(page.revisions.count(), revisions)


class CommitTests(ApplySummariesTestCase):
    def test_commit_sets_summary_only_and_publishes_one_logged_revision(self):
        page = self.site("Our Lady of Somewhere", "somewhere", locality="A Town", country="France")
        trail = PilgrimageTrailPage(title="A Long Trail", slug="a-long-trail", summary_short=LONG)
        self.routes.add_child(instance=trail)
        trail.save_revision().publish()
        before = page.revisions.count()
        out = self.run_cmd([
            {"title": "Our Lady of Somewhere", "summary_short": "Short and sweet.",
             "url_path_hint": "/marian-apparitions/somewhere/"},
            {"title": "A Long Trail", "summary_short": "A short trail line."},
        ], "--commit")
        self.assertIn("Changed and published: 2; unchanged 0; skipped 0.", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(page.summary_short, "Short and sweet.")
        self.assertEqual((page.locality, page.country, page.title), ("A Town", "France", "Our Lady of Somewhere"))
        self.assertTrue(page.live)
        self.assertFalse(page.has_unpublished_changes)
        self.assertEqual(page.revisions.count(), before + 1)
        self.assertEqual(page.live_revision_id, page.latest_revision_id)
        self.assertTrue(PageLogEntry.objects.filter(page=page, action="wagtail.edit").exists())
        self.assertTrue(PageLogEntry.objects.filter(page=page, action="wagtail.publish").exists())
        self.assertEqual(PilgrimageTrailPage.objects.get(pk=trail.pk).summary_short, "A short trail line.")
        self.assertIn("Unchanged", self.run_cmd([{"title": "A Long Trail", "summary_short": "A short trail line."}], "--commit"))


class SkipTests(ApplySummariesTestCase):
    def test_an_ambiguous_title_is_skipped(self):
        a = self.site("Twin Shrine", "twin-shrine")
        b = self.site("Twin Shrine", "twin-shrine", parent=self.routes)
        out = self.run_cmd([{"title": "Twin Shrine", "summary_short": "Short."}], "--commit")
        self.assertIn("SKIPPED 'Twin Shrine': 2 live site/trail page(s) titled exactly this", out)
        for page in (a, b):
            page.refresh_from_db()
            self.assertEqual(page.summary_short, LONG)

    def test_a_url_path_hint_picks_one_and_a_wrong_hint_or_title_is_skipped(self):
        self.site("Twin Shrine", "twin-shrine")
        b = self.site("Twin Shrine", "twin-shrine", parent=self.routes)
        out = self.run_cmd([
            {"title": "Twin Shrine", "summary_short": "Short.", "url_path_hint": "/pilgrimage-routes/twin-shrine/"},
            {"title": "Twin Shrine", "summary_short": "Short.", "url_path_hint": "/nowhere/twin-shrine/"},
            {"title": "No Such Shrine", "summary_short": "Short."},
        ])
        self.assertIn(f"[1] Would change #{b.pk}", out)
        self.assertIn("[2] SKIPPED 'Twin Shrine': 0 live site/trail page(s) titled exactly this at /nowhere/twin-shrine/", out)
        self.assertIn("[3] SKIPPED 'No Such Shrine': 0 live", out)

    def test_a_page_with_a_pending_draft_is_skipped_and_its_draft_stays_unpublished(self):
        page = self.site("Drafty Shrine", "drafty-shrine")
        page.locality = "Draft edit"
        page.save_revision()
        out = self.run_cmd([{"title": "Drafty Shrine", "summary_short": "Short."}], "--commit")
        self.assertIn("the page has unpublished changes", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(page.summary_short, LONG)
        self.assertTrue(page.has_unpublished_changes)
        self.assertNotEqual(page.locality, "Draft edit", "the draft was not published")

    def test_text_over_200_characters_and_duplicates_are_skipped(self):
        page = self.site("Our Lady of Somewhere", "somewhere")
        out = self.run_cmd([
            {"title": "Our Lady of Somewhere", "summary_short": "x" * 201},
            {"title": "Our Lady of Somewhere", "summary_short": "Short."},
        ], "--commit")
        self.assertIn("new text is 201 characters (limit 200)", out)
        self.assertIn("[2] SKIPPED", out)
        self.assertIn("a second entry for the same page", out)
        page.refresh_from_db()
        self.assertEqual(page.summary_short, LONG)
