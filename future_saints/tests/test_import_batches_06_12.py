"""Content batches 06-12 through import_learning_pages: several eucharistic and Holy Land pages in
one file (the real batch 11 and 12 files, against fixture adult pages titled exactly like
production), a null production_id_hint resolved by exact title (one match links; none, two, or a
non-Holy-Land page stop the page), per-page review notes (--review-note-for), and "Their Story"
on a saint page stored as "The Story" with a warning (owner decision, 2026-11-19)."""
import copy
import hashlib
import json
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.models import WorkflowState

from catalog.models import SacredSitePage, SaintPage
from future_saints.models import EucharisticLearningPage, FutureSaintsIndexPage, HolyLandLearningPage, SaintLearningPage

from .base import FutureSaintsTestCase

CONTENT = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content"
HASHES = {
    "06": "66f66edfaf76deb1c9d779fc1e12df0600d274de70c93e7c3009c489ea890e57",
    "07": "e4d8da591418fea74fbaae497a956ee7488b47b57edee93ac4e01c25fab04f6d",
    "08": "bfbb34806d16a3e80d9bf6a813cf32d0e7c46a8bdfe329b51e5ea017193549e9",
    "09": "85e432918fdb32b273595da3e2af22975d654781aad6c03c6f5ebebef8b22882",
    "10": "adb5406a07a80bd05f3daaa9b87f708747cd962fdd7028d7c161c68f78b7ba51",
    "11": "2d75fb1345566d30a77bd5af5ac689f694893e00037b60d71d2705dfc31c9763",
    "12": "590cfc0b9dc326f7d92d82da8984a11043a4e316193fa18039b30f483b35178e",
}
CATEGORY = {"eucharistic": "Eucharistic Miracle", "holy_land": "Holy Land"}


def batch(n):
    return CONTENT / f"future-saints-batch-{n}.json"


def base_note(n):
    return f"Imported from content batch {n} on 2026-11-19. Text review by Steven pending. " \
           f"Notes: claude/future-saints-content-batch-{n}.md"


class Batches0612TestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        self.data = {n: json.loads(batch(n).read_text(encoding="utf-8")) for n in ("11", "12")}
        self.sites = {}
        for n, data in self.data.items():
            for row in data["pages"]:
                site = SacredSitePage(title=row["canonical"]["match_title"], slug=f"fixture-{row['slug']}",
                                      category=CATEGORY[row["kind"]])
                self.home.get_parent().add_child(instance=site)
                self.sites[row["slug"]] = site
        self.tmp = tempfile.mkdtemp()

    def run_import(self, path, *flags):
        out = StringIO()
        call_command("import_learning_pages", str(path), *flags, stdout=out)
        return out.getvalue()

    def failing(self, data, *flags):
        path = os.path.join(self.tmp, "pages.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("import_learning_pages", path, *flags, stdout=out)
        return out.getvalue()


class FileTests(Batches0612TestCase):
    def test_the_seven_files_are_the_approved_copies(self):
        total = 0
        for n, digest in HASHES.items():
            raw = batch(n).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, n)
            total += len(json.loads(raw)["pages"])
        self.assertEqual(total, 50)


class MultiPageTypeTests(Batches0612TestCase):
    def test_five_eucharistic_pages_in_one_file(self):
        out = self.run_import(batch("11"), "--review-note", base_note("11"))
        self.assertIn("Changed: 5 (created 5, updated 0); unchanged 0; skipped 0; failed 0.", out)
        index = FutureSaintsIndexPage.objects.get(slug="eucharistic-miracles")
        for row in self.data["11"]["pages"]:
            page = EucharisticLearningPage.objects.get(slug=row["slug"])
            self.assertFalse(page.live, row["slug"])
            self.assertEqual(page.get_parent().pk, index.pk)
            self.assertEqual(page.canonical_id, self.sites[row["slug"]].pk)
            self.assertTrue(page.belief and page.reported and page.church_says, row["slug"])
            self.assertEqual(page.review_note, base_note("11"))
            self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists())
        self.assertIn("Verify: 0 differences.", self.run_import(batch("11"), "--verify", "--review-note", base_note("11")))
        self.assertIn("unchanged 5", self.run_import(batch("11"), "--review-note", base_note("11")))

    def test_five_holy_land_pages_in_one_file_with_null_hints(self):
        out = self.run_import(batch("12"), "--dry-run")
        for row in self.data["12"]["pages"]:
            self.assertIsNone(row["canonical"]["production_id_hint"])
            site = self.sites[row["slug"]]
            self.assertIn(f"canonical: #{site.pk} {site.title!r}  (no production_id_hint: resolved by exact title, "
                          f"1 live match)", out)
        self.run_import(batch("12"))
        index = FutureSaintsIndexPage.objects.get(slug="holy-land")
        for row in self.data["12"]["pages"]:
            page = HolyLandLearningPage.objects.get(slug=row["slug"])
            self.assertEqual(page.get_parent().pk, index.pk)
            self.assertEqual(page.canonical_id, self.sites[row["slug"]].pk)
            self.assertEqual(page.story_label, "The Bible Story")
            self.assertEqual(page.bible_references.count(), len(row["type_specific"]["bible_references"]))
        self.assertIn("Verify: 0 differences.", self.run_import(batch("12"), "--verify"))


class NullHintTests(Batches0612TestCase):
    def one_page(self):
        data = copy.deepcopy(self.data["12"])
        data["pages"] = data["pages"][:1]
        return data, data["pages"][0]

    def test_no_match_stops_the_page(self):
        data, row = self.one_page()
        self.sites[row["slug"]].unpublish()
        out = self.failing(data)
        self.assertIn(f"0 live catalog.SacredSitePage page(s) titled exactly {row['canonical']['match_title']!r}", out)

    def test_two_matches_stop_the_page(self):
        data, row = self.one_page()
        twin = SacredSitePage(title=row["canonical"]["match_title"], slug="fixture-twin", category="Holy Land")
        self.home.get_parent().add_child(instance=twin)
        out = self.failing(data)
        self.assertIn(f"2 live catalog.SacredSitePage page(s) titled exactly {row['canonical']['match_title']!r}", out)

    def test_a_match_outside_the_holy_land_stops_the_page(self):
        data, row = self.one_page()
        site = self.sites[row["slug"]]
        site.category = "Shrine & Basilica"
        site.save_revision().publish()
        out = self.failing(data)
        self.assertIn("isn't an allowed canonical page for HolyLandLearningPage", out)


class ReviewNoteForTests(Batches0612TestCase):
    EXTRA = "Thin sourcing; see notes."

    def note_for(self, slug, n="11"):
        return (f"Imported from content batch {n} on 2026-11-19. Text review by Steven pending. {self.EXTRA} "
                f"Notes: claude/future-saints-content-batch-{n}.md")

    def test_one_page_gets_its_own_note_the_rest_the_file_note(self):
        slug = "eucharistic-miracle-of-faverney"
        flags = ("--review-note", base_note("11"), "--review-note-for", f"{slug}={self.note_for(slug)}")
        out = self.run_import(batch("11"), *flags)
        self.assertIn(f"review note: {self.note_for(slug)!r}", out)
        self.assertEqual(EucharisticLearningPage.objects.get(slug=slug).review_note, self.note_for(slug))
        others = EucharisticLearningPage.objects.exclude(slug=slug).values_list("review_note", flat=True)
        self.assertEqual(set(others), {base_note("11")})
        self.assertIn("Verify: 0 differences.", self.run_import(batch("11"), "--verify", *flags))

    def test_bad_review_note_for_is_refused_before_anything_is_written(self):
        for flags in (("--review-note-for", "not-in-this-file=Note."),
                      ("--review-note-for", "no-equals-sign"),
                      ("--review-note-for", "eucharistic-miracle-of-turin=" + "x" * 256),
                      ("--review-note-for", "eucharistic-miracle-of-turin=A.",
                       "--review-note-for", "eucharistic-miracle-of-turin=B.")):
            with self.assertRaises(CommandError, msg=flags):
                self.run_import(batch("11"), *flags)
        self.assertFalse(EucharisticLearningPage.objects.exists())


class TheirStoryTests(Batches0612TestCase):
    def test_their_story_is_stored_as_the_story_with_a_warning(self):
        data = json.loads(batch("10").read_text(encoding="utf-8"))
        data["pages"] = [p for p in data["pages"] if p["slug"] == "charles-lwanga-and-companions"]
        row = data["pages"][0]
        self.assertEqual(row["story_label"], "Their Story")
        self.home.get_parent().add_child(instance=SaintPage(title=row["canonical"]["match_title"], slug="fixture-lwanga"))
        path = os.path.join(self.tmp, "lwanga.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        out = self.run_import(path, "--dry-run")
        self.assertIn('warning: story_label \'Their Story\' has no saint choice; the heading shows "The Story"', out)
        self.run_import(path)
        page = SaintLearningPage.objects.get(slug="charles-lwanga-and-companions")
        self.assertEqual(page.story_label, "the")
        self.assertEqual(page.story_heading, "The Story")
        self.assertIn("Verify: 0 differences.", self.run_import(path, "--verify"))
        other = copy.deepcopy(data)
        other["pages"][0]["story_label"] = "Their Tale"
        self.assertIn("story_label 'Their Tale' must be one of", self.failing(other))
