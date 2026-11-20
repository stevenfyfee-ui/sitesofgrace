"""Directory cards and the long-summary worklist.

What these protect: report_long_summaries lists only live sites, trails and
saints whose card text is over the limit, longest first, and changes nothing;
the directory template gives every card the uniform grid, a full-text bio (the
clamp is CSS, the text is never cut on the server) and one "Read more" cue that
is not a second link.
"""
import re
from io import StringIO

from django.core.management import call_command
from wagtail.models import Site

from catalog.models import PilgrimageTrailPage, SacredSitePage, SaintPage
from catalog.tests import SacredSitePageTestCase
from home.models import StandardPage


class LongSummaryTestCase(SacredSitePageTestCase):
    def setUp(self):
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        super().setUp()
        self.directory = StandardPage(title="Marian Apparitions", slug="marian-apparitions",
                                      layout="category_directory")
        self.site_root().add_child(instance=self.directory)

    def add(self, model, title, live=True, **fields):
        if model is SacredSitePage:
            fields.setdefault("category", "Marian Apparition")
        page = model(title=title, slug=title.lower().replace(" ", "-"), live=live, **fields)
        self.directory.add_child(instance=page)
        return page

    def report(self, *args):
        out = StringIO()
        call_command("report_long_summaries", *args, stdout=out)
        return out.getvalue()


class ReportTests(LongSummaryTestCase):
    def test_lists_long_live_text_longest_first_and_changes_nothing(self):
        site = self.add(SacredSitePage, "Long Site", summary_short="s" * 250)
        trail = self.add(PilgrimageTrailPage, "Long Trail", summary_short="t" * 900)
        saint = self.add(SaintPage, "Long Saint", significance="g" * 201)
        self.add(SacredSitePage, "Short Site", summary_short="s" * 200)
        self.add(SacredSitePage, "Draft Site", live=False, summary_short="d" * 999)
        out = self.report()
        self.assertIn("3 live page(s) with card text over 200 characters", out)
        lines = [line for line in out.splitlines() if re.match(r"\s*\d+  ", line)]
        self.assertEqual([line.split()[0] for line in lines], ["900", "250", "201"])
        self.assertIn("Trail  Long Trail  (summary_short)", lines[0])
        self.assertIn("Saint  Long Saint  (significance)", lines[2])
        self.assertIn(f"/admin/pages/{site.pk}/edit/", out)
        self.assertIn("/marian-apparitions/long-trail/", out)
        self.assertNotIn("Short Site", out)
        self.assertNotIn("Draft Site", out)
        for page, field, value in ((site, "summary_short", "s" * 250), (trail, "summary_short", "t" * 900),
                                   (saint, "significance", "g" * 201)):
            page.refresh_from_db()
            self.assertEqual(getattr(page, field), value, "read-only")

    def test_limit_option(self):
        self.add(SacredSitePage, "Medium Site", summary_short="m" * 170)
        self.assertIn("0 live page(s)", self.report())
        self.assertIn("1 live page(s) with card text over 160 characters", self.report("--limit", "160"))


class DirectoryCardTests(LongSummaryTestCase):
    def test_every_card_is_uniform_with_full_text_and_one_read_more_cue(self):
        long_text = "A long summary. " * 40
        self.add(SacredSitePage, "Long Site", summary_short=long_text)
        self.add(SacredSitePage, "Short Site", summary_short="One sentence.")
        self.add(SacredSitePage, "Blank Site", summary_short="")
        html = self.client.get(StandardPage.objects.get(pk=self.directory.pk).url).content.decode()
        self.assertIn('class="directory-grid directory-grid--uniform"', html)
        cards = re.findall(r'<a class="directory-card"[^>]*>(.*?)</a>', html, re.S)
        self.assertEqual(len(cards), 3)
        for card in cards:
            self.assertEqual(card.count('class="directory-card-more"'), 1)
            self.assertEqual(card.count("<p>"), 1, "a blank bio still keeps the card's shape")
            self.assertNotIn("<a ", card, "Read more is a cue, not a nested link")
        self.assertIn(long_text.strip(), html, "the text is clamped by CSS, never cut on the server")
