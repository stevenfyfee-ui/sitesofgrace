"""Tests for sync_catalog, the one command that composes import_catalog,
apply_enrichment, merge_saints and stub_saints for a single production
paste.

The one thing this suite has to prove, because it's the one thing that
matters before this goes anywhere near production: running the command
twice against the same data is a clean no-op the second time. Everything
else (stop conditions aborting the whole transaction) is secondary to that.
"""
import csv
import os
import shutil
import tempfile

import openpyxl
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Site
from wagtail.test.utils import WagtailPageTestCase

from catalog.models import SaintPage
from home.models import StandardPage

WORKBOOK_HEADER = [
    "name", "slug", "also_known_as", "honorific_type", "feast_day", "born",
    "died", "canonized", "patronage", "significance", "body_draft",
    "source_url", "source_note", "data_status", "editor_notes",
]

ENRICHMENT_HEADER = ["slug", "confidence", "qid", "order", "burial", "image_url", "image_credit"]


class SyncCatalogTestCase(WagtailPageTestCase):
    """Fixture models one duplicate pair, one hidden stub-with-content pair,
    and one already-enriched field, matching the real shape of the
    production run this command was built for: import_catalog finds
    everything already in place (created=0, updated=0), and the real work
    is in enrichment, merging the known duplicates, and publishing the
    stubs that now have content."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        site = Site.objects.get(is_default_site=True)
        self.saints_index = StandardPage(title="Saints", slug="saints")
        site.root_page.add_child(instance=self.saints_index)

        # Hidden stubs that already have narrative content -- these are the
        # "winners" of the two known duplicate pairs, and the two pages
        # stub_saints --publish --ready should bring live.
        self.winner1 = SaintPage(
            title="St. Birgitta - Bridget of Sweden",
            slug="st-birgitta-bridget-of-sweden",
            significance="Founded the Bridgettine order.",
            data_status="stub-import",
            live=False,
        )
        self.saints_index.add_child(instance=self.winner1)

        self.winner2 = SaintPage(
            title="St. John Leonardi",
            slug="st-john-leonardi",
            significance="Founded the Clerics Regular of the Mother of God.",
            data_status="stub-import",
            live=False,
        )
        self.saints_index.add_child(instance=self.winner2)

        # The duplicate "losers" -- ordinary live pages, not stubs, exactly
        # like the two real duplicate pages this command was written for.
        self.loser1 = SaintPage(
            title="St. Bridget of Sweden",
            slug="st-bridget-of-sweden",
            also_known_as="Birgitta of Sweden",
            live=True,
        )
        self.saints_index.add_child(instance=self.loser1)

        self.loser2 = SaintPage(
            title="St. Giovanni Leonardi",
            slug="st-giovanni-leonardi",
            live=True,
        )
        self.saints_index.add_child(instance=self.loser2)

        # Already live and NOT a stub -- e.g. a saint that predates this
        # workbook under the same title. The workbook still marks its row
        # stub-* with real significance (it doesn't know this page already
        # graduated), so import_catalog updates its content but stub_saints
        # never counts it, since it was never hidden. This is the exact
        # shape of the real "7 eligible, expected 8" production mismatch.
        self.already_live = SaintPage(
            title="St. Already Live",
            slug="st-already-live",
            significance="Original significance, already published.",
            data_status="",
            live=True,
        )
        self.saints_index.add_child(instance=self.already_live)

        self.workbook_path = os.path.join(self.tmpdir, "catalog.xlsx")
        self.enrichment_csv_path = os.path.join(self.tmpdir, "enrichment.csv")
        self._write_workbook_matching_current_state()
        self._write_enrichment_csv()

    def _write_workbook_matching_current_state(self):
        """Every row for winner1/winner2/loser1/loser2 matches what's
        already in the database -- the workbook is not the thing changing
        anything for them in this test. That's deliberate: it isolates the
        import step's own idempotency (a second run finding nothing to
        update) from the enrichment/merge/publish steps, which is the
        actual new work sync_catalog does.

        already_live is the one exception, on purpose: its workbook row
        carries new significance and a stub-* data_status even though the
        page is already live and not a stub -- exactly the mismatch behind
        the real "7 eligible, expected 8" production incident."""
        rows = [
            {
                "name": p.title, "slug": p.slug, "also_known_as": p.also_known_as,
                "honorific_type": "", "feast_day": "", "born": "", "died": "",
                "canonized": "", "patronage": "", "significance": p.significance,
                "body_draft": "", "source_url": "", "source_note": "",
                "data_status": p.data_status, "editor_notes": "",
            }
            for p in (self.winner1, self.winner2, self.loser1, self.loser2)
        ]
        rows.append({
            "name": self.already_live.title, "slug": self.already_live.slug, "also_known_as": "",
            "honorific_type": "", "feast_day": "", "born": "", "died": "",
            "canonized": "", "patronage": "",
            "significance": "Updated significance from the workbook.",
            "body_draft": "", "source_url": "", "source_note": "",
            "data_status": "stub-import", "editor_notes": "",
        })
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Saints"
        ws.append(WORKBOOK_HEADER)
        for row in rows:
            ws.append([row.get(col, "") for col in WORKBOOK_HEADER])
        wb.save(self.workbook_path)

    def _write_enrichment_csv(self):
        rows = [
            {"slug": "st-birgitta-bridget-of-sweden", "confidence": "label",
             "qid": "Q229015", "order": "Bridgettines", "burial": "Vadstena Abbey",
             "image_url": "", "image_credit": ""},
            {"slug": "st-john-leonardi", "confidence": "label",
             "qid": "Q353860", "order": "Clerics Regular of the Mother of God",
             "burial": "", "image_url": "", "image_credit": ""},
        ]
        with open(self.enrichment_csv_path, "w", newline="", encoding="utf8") as fh:
            writer = csv.DictWriter(fh, fieldnames=ENRICHMENT_HEADER)
            writer.writeheader()
            writer.writerows(rows)

    def run_sync(self, dry_run=False, **overrides):
        options = {
            "workbook": self.workbook_path,
            "enrichment_csv": self.enrichment_csv_path,
            "min_enriched": 2,
            "expect_published": 2,
        }
        options.update(overrides)
        if dry_run:
            options["dry_run"] = True
        call_command("sync_catalog", **options)

    def test_first_run_enriches_merges_and_publishes(self):
        self.run_sync()

        self.winner1.refresh_from_db()
        self.winner2.refresh_from_db()
        self.loser1.refresh_from_db()
        self.loser2.refresh_from_db()

        self.assertEqual(self.winner1.wikidata_id, "Q229015")
        self.assertEqual(self.winner1.burial_place, "Vadstena Abbey")
        self.assertEqual(self.winner2.wikidata_id, "Q353860")

        # merge_saints: aka transferred, losers unpublished, redirects made.
        self.assertIn("Birgitta of Sweden", self.winner1.also_known_as)
        self.assertFalse(self.loser1.live)
        self.assertFalse(self.loser2.live)
        self.assertTrue(Redirect.objects.filter(redirect_page_id=self.winner1.pk).exists())
        self.assertTrue(Redirect.objects.filter(redirect_page_id=self.winner2.pk).exists())

        # stub_saints --publish --ready: both content-bearing stubs go live.
        self.assertTrue(self.winner1.live)
        self.assertEqual(self.winner1.data_status, "")
        self.assertTrue(self.winner2.live)
        self.assertEqual(self.winner2.data_status, "")

    def test_second_run_is_a_clean_no_op(self):
        """The whole point of this suite: run it twice, and the second run
        must report zero everywhere except total-live. If this ever fails,
        do not run sync_catalog against production until it's fixed again --
        that was the explicit instruction that produced this test."""
        self.run_sync()

        out = tempfile.TemporaryFile(mode="w+")
        call_command(
            "sync_catalog",
            workbook=self.workbook_path,
            enrichment_csv=self.enrichment_csv_path,
            min_enriched=0,
            expect_published=0,
            stdout=out,
        )
        out.seek(0)
        summary = out.read()

        self.assertIn("created=0", summary)
        self.assertIn("updated=0", summary)
        self.assertIn("enriched=0", summary)
        self.assertIn("merged=0", summary)
        self.assertIn("published=0", summary)

    def test_dry_run_changes_nothing(self):
        saints_before = SaintPage.objects.count()
        self.run_sync(dry_run=True)

        self.winner1.refresh_from_db()
        self.assertEqual(self.winner1.wikidata_id, "")
        self.assertTrue(self.loser1.live)
        self.assertEqual(SaintPage.objects.count(), saints_before)
        self.assertFalse(Redirect.objects.filter(redirect_page_id=self.winner1.pk).exists())

    def test_aborts_and_rolls_back_when_a_page_would_be_created(self):
        wb = openpyxl.load_workbook(self.workbook_path)
        ws = wb["Saints"]
        ws.append([
            "St. New Saint Nobody Reviewed", "st-new-saint-nobody-reviewed",
            "", "", "", "", "", "", "", "Some significance.", "", "", "", "", "",
        ])
        wb.save(self.workbook_path)

        saints_before = SaintPage.objects.count()
        with self.assertRaises(CommandError):
            self.run_sync()

        self.assertEqual(SaintPage.objects.count(), saints_before)
        self.winner1.refresh_from_db()
        self.assertEqual(self.winner1.wikidata_id, "", "a stop condition must roll back the WHOLE transaction")

    def test_aborts_when_enrichment_touches_far_fewer_rows_than_expected(self):
        with self.assertRaises(CommandError):
            self.run_sync(min_enriched=1000)

        self.winner1.refresh_from_db()
        self.assertEqual(self.winner1.wikidata_id, "", "a stop condition must roll back the WHOLE transaction")
        self.assertTrue(self.loser1.live, "merge_saints must not have committed either")

    def test_aborts_when_published_count_is_not_the_expected_count(self):
        with self.assertRaises(CommandError):
            self.run_sync(expect_published=99)

        self.winner1.refresh_from_db()
        self.assertFalse(self.winner1.live, "a stop condition must roll back the WHOLE transaction")

    def test_publish_mismatch_error_names_the_already_live_page(self):
        """The real incident this reproduces: a workbook row is stub-tagged
        with real content, but the page is already live, so stub_saints
        never counts it. The error must name it and say why, not just
        report a bare count that sends someone hunting."""
        with self.assertRaises(CommandError) as ctx:
            self.run_sync(expect_published=3)

        message = str(ctx.exception)
        self.assertIn("St. Already Live", message)
        self.assertIn("already live BEFORE this run", message)
        self.assertIn("St. Birgitta - Bridget of Sweden", message, "must also name what WAS published")
        self.assertIn("St. John Leonardi", message)

        self.already_live.refresh_from_db()
        self.assertEqual(
            self.already_live.significance, "Original significance, already published.",
            "a stop condition must roll back the WHOLE transaction, including this content update",
        )
