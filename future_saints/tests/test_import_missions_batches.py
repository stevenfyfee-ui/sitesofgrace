"""import_learning_pages on the four California missions files (batches A-D, founding #2-#21):
five pages per file, the review note on every mission page, the year-only founding date
(#6 Dolores: an empty date, display "1776", --verify a match), a display less precise than
the date (#7 San Juan Capistrano), the fixed quick-fact icons, source URLs stored unchanged,
and the San Diego page (#1) left alone. The canonical pages are fixtures with the exact
production titles, all on a fixture Mission Trail."""
import hashlib
import json
import os
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from wagtail.models import WorkflowState

from catalog.models import PilgrimageTrailPage, SacredSitePage, TrailStop
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.models import FutureSaintsIndexPage, MissionLearningPage

from .base import FutureSaintsTestCase

CONTENT = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content"
BATCHES = {
    "a": "a17138fdfda2961d20839b3c67a595adc902c31a356560848f7d7f26a175c673",
    "b": "317a09ee06437dace42a1ddd99555ec5ae96a672c43b10d330827ad0e6af3352",
    "c": "742f4238b156fbcca7f388e182d592064032a723ee0dbec74a0803bf2ba0357a",
    "d": "ede317d2aa38f032e593ce331770d00986805593033ae15eac9a2ef07b9a1ec4",
}
SAN_DIEGO = "mission-san-diego-de-alcala.json"


def batch_path(x):
    return CONTENT / f"future-saints-missions-batch-{x}.json"


def review_note(x):
    return (f"Imported from missions batch {x} on 2026-11-14. Text review by Steven pending. Needs a reader "
            f"from the tribe named on the page before publishing. Notes: claude/future-saints-content-missions-batch-{x}.md")


class MissionBatchesTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        root = self.home.get_parent()
        self.data = {x: json.loads(batch_path(x).read_text(encoding="utf-8")) for x in BATCHES}
        self.san_diego = json.loads((CONTENT / SAN_DIEGO).read_text(encoding="utf-8"))
        rows = [self.san_diego["pages"][0]] + [p for x in BATCHES for p in self.data[x]["pages"]]
        trail = PilgrimageTrailPage(title="Fixture Mission Trail", slug=MISSION_TRAIL_SLUG)
        self.canonicals, stops = {}, []
        for i, row in enumerate(rows):
            site = SacredSitePage(title=row["canonical"]["match_title"], slug=f"fixture-{row['slug']}",
                                  category="Shrine & Basilica")
            root.add_child(instance=site)
            self.canonicals[row["slug"]] = site
            stops.append(TrailStop(site=site, sort_order=i))
        trail.stops = stops
        root.add_child(instance=trail)
        self.tmp = tempfile.mkdtemp()

    def run_import(self, x, *flags):
        out = StringIO()
        call_command("import_learning_pages", str(batch_path(x)), *flags, stdout=out)
        return out.getvalue()

    def import_all(self):
        for x in BATCHES:
            self.run_import(x, "--review-note", review_note(x))

    def page(self, slug):
        return MissionLearningPage.objects.get(slug=slug)


class FileTests(MissionBatchesTestCase):
    def test_the_files_are_the_approved_copies(self):
        for x, digest in BATCHES.items():
            with self.subTest(x):
                self.assertEqual(hashlib.sha256(batch_path(x).read_bytes()).hexdigest(), digest)
                self.assertEqual(len(self.data[x]["pages"]), 5)
        numbers = [p["founding_number"] for x in BATCHES for p in self.data[x]["pages"]]
        self.assertEqual(numbers, list(range(2, 22)))


class ImportTests(MissionBatchesTestCase):
    def test_each_multi_page_file_dry_runs_imports_verifies_and_reruns(self):
        index = FutureSaintsIndexPage.objects.get(slug="california-missions")
        for x in BATCHES:
            with self.subTest(x):
                out = self.run_import(x, "--dry-run", "--review-note", review_note(x))
                self.assertEqual(out.count("Would create (draft)"), 5)
                self.assertIn("Would change: 5 (created 5, updated 0)", out)
                self.assertFalse(MissionLearningPage.objects.filter(
                    slug__in=[p["slug"] for p in self.data[x]["pages"]]).exists(), "a dry run writes nothing")
                out = self.run_import(x, "--review-note", review_note(x))
                self.assertIn("Changed: 5 (created 5, updated 0)", out)
                for row in self.data[x]["pages"]:
                    page = self.page(row["slug"])
                    self.assertFalse(page.live)
                    self.assertEqual(page.get_parent().pk, index.pk)
                    self.assertEqual(page.canonical_id, self.canonicals[row["slug"]].pk)
                    self.assertEqual(page.founding_number, row["founding_number"])
                    self.assertEqual(page.story_label, "The Mission Story")
                    self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists(), "never submitted")
                self.assertIn("Verify: 0 differences.", self.run_import(x, "--verify", "--review-note", review_note(x)))
                self.assertIn("Changed: 0", self.run_import(x, "--review-note", review_note(x)))
        self.assertEqual(MissionLearningPage.objects.child_of(index).count(), 20)

    def test_review_note_is_set_on_every_mission_page(self):
        self.import_all()
        for x in BATCHES:
            self.assertLessEqual(len(review_note(x)), 255)
            for row in self.data[x]["pages"]:
                self.assertEqual(self.page(row["slug"]).review_note, review_note(x), row["slug"])

    def test_quick_facts_and_source_urls_are_stored_as_given(self):
        self.import_all()
        for x in BATCHES:
            for row in self.data[x]["pages"]:
                page = self.page(row["slug"])
                facts = list(page.quick_facts.order_by("sort_order"))
                self.assertEqual([f.icon for f in facts], ["number", "calendar", "person", "star", "people"], row["slug"])
                self.assertEqual([f.value for f in facts], [q["value"] for q in row["quick_facts"]])
                self.assertEqual([s.url for s in page.sources.order_by("sort_order")], [s["url"] for s in row["sources"]])
        urls = {s.url for p in MissionLearningPage.objects.all() for s in p.sources.all()}
        self.assertIn("https://www.nps.gov/articles/000/mission-san-miguel-arcàngel-ca.htm", urls)
        self.assertIn("https://www.nps.gov/articles/000/mission-santa-in%C3%A9s-ca.htm", urls)

    def test_san_diego_is_left_alone(self):
        path = os.path.join(self.tmp, SAN_DIEGO)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.san_diego, fh, ensure_ascii=False)
        call_command("import_learning_pages", path, stdout=StringIO())
        san_diego = self.page("mission-san-diego-de-alcala")
        revisions = san_diego.revisions.count()
        self.import_all()
        san_diego.refresh_from_db()
        self.assertEqual(san_diego.revisions.count(), revisions)
        self.assertEqual(san_diego.founding_date, date(1769, 7, 16))
        self.assertEqual(san_diego.review_note, "")


class FoundingDateTests(MissionBatchesTestCase):
    def test_a_year_only_founding_date_is_stored_empty_with_the_display_as_given(self):
        row = next(p for p in self.data["a"]["pages"] if p["founding_number"] == 6)
        self.assertEqual((row["founding_date"], row["founding_date_display"]), ("1776", "1776"))
        out = self.run_import("a", "--dry-run")
        self.assertIn("founding: #6, date EMPTY (the file gives the year only, '1776'), display '1776'", out)
        self.run_import("a")
        page = self.page("mission-san-francisco-de-asis")
        self.assertIsNone(page.founding_date)
        self.assertIsNone(page.get_latest_revision_as_object().founding_date)
        self.assertEqual(page.founding_date_display, "1776")
        self.assertEqual(page.founding_source_note, row["founding_source_note"])
        page.full_clean()
        out = self.run_import("a", "--verify")
        self.assertIn("mission-san-francisco-de-asis/  #%d draft (unpublished): 0 difference(s)" % page.pk, out)
        self.assertIn("Verify: 0 differences.", out)

    def test_a_display_less_precise_than_the_date_is_imported_as_given(self):
        self.run_import("b")
        page = self.page("mission-san-juan-capistrano")
        self.assertEqual(page.founding_date, date(1776, 11, 1))
        self.assertEqual(page.founding_date_display, "1776")
        self.assertEqual(page.canonical.title, "Mission Basilica San Juan Capistrano")

    def test_other_partial_dates_still_stop(self):
        data = json.loads(batch_path("a").read_text(encoding="utf-8"))
        data["pages"] = data["pages"][:1]
        for bad in ("1776-06", "177", "June 1776"):
            with self.subTest(bad):
                data["pages"][0]["founding_date"] = bad
                path = os.path.join(self.tmp, "bad.json")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
                out = StringIO()
                with self.assertRaises(Exception):
                    call_command("import_learning_pages", path, stdout=out)
                self.assertIn("founding_date must be an ISO date like 1769-07-16, or a year like 1776", out.getvalue())
                self.assertFalse(MissionLearningPage.objects.exists())
