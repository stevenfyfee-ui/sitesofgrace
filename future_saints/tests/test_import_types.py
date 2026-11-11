"""import_learning_pages for the four non-saint types, run on the approved
content files (Lourdes, Lanciano, Holy Sepulchre, Mission San Diego): each
type_specific key lands on its field, Bible references keep JSON order and read
back unchanged, the mission founding fields and their rules, the free-text
story heading, the person / people / number icons, and the stop on a key with
no field. The canonical pages are fixtures with the exact production titles."""
import copy
import json
import os
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.html import escape
from wagtail.models import WorkflowState

from catalog.models import PilgrimageTrailPage, SacredSitePage, TrailStop
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.models import (
    EucharisticLearningPage,
    FutureSaintsIndexPage,
    HolyLandLearningPage,
    MarianLearningPage,
    MissionLearningPage,
)

from .base import FS_ON, FutureSaintsTestCase

CONTENT = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content"
FILES = {
    "lourdes": ("our-lady-of-lourdes.json", MarianLearningPage, "Marian Apparition"),
    "lanciano": ("eucharistic-miracle-of-lanciano.json", EucharisticLearningPage, "Eucharistic Miracle"),
    "sepulchre": ("church-of-the-holy-sepulchre.json", HolyLandLearningPage, "Holy Land"),
    "san_diego": ("mission-san-diego-de-alcala.json", MissionLearningPage, "Shrine & Basilica"),
}


def para(text):
    return f"<p>{escape(text)}</p>"


class FourFilesTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        root = self.home.get_parent()
        self.data, self.canonicals = {}, {}
        for key, (name, _, category) in FILES.items():
            self.data[key] = json.loads((CONTENT / name).read_text(encoding="utf-8"))
            title = self.data[key]["pages"][0]["canonical"]["match_title"]
            site = SacredSitePage(title=title, slug=f"fixture-{key.replace('_', '-')}", category=category)
            root.add_child(instance=site)
            self.canonicals[key] = site
        trail = PilgrimageTrailPage(title="Fixture Mission Trail", slug=MISSION_TRAIL_SLUG)
        trail.stops = [TrailStop(site=self.canonicals["san_diego"], sort_order=0)]
        root.add_child(instance=trail)
        self.tmp = tempfile.mkdtemp()

    def row(self, key):
        return self.data[key]["pages"][0]

    def run_import(self, key, *flags, data=None):
        path = os.path.join(self.tmp, f"{key}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data or self.data[key], fh, ensure_ascii=False)
        out = StringIO()
        call_command("import_learning_pages", path, *flags, stdout=out)
        return out.getvalue()

    def failing(self, key, change):
        data = copy.deepcopy(self.data[key])
        change(data["pages"][0])
        out = StringIO()
        with self.assertRaises(CommandError):
            path = os.path.join(self.tmp, f"{key}-bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            call_command("import_learning_pages", path, stdout=out)
        self.assertFalse(FILES[key][1].objects.filter(slug=data["pages"][0]["slug"]).exists(), "nothing written")
        return out.getvalue()

    def page(self, key):
        return FILES[key][1].objects.get(slug=self.row(key)["slug"])


class FileFitTests(FourFilesTestCase):
    def test_all_four_dry_run_then_import_verify_and_rerun(self):
        for key, (_, model, _) in FILES.items():
            with self.subTest(key):
                out = self.run_import(key, "--dry-run")
                self.assertIn("Would create (draft)", out)
                self.assertIn(f"canonical: #{self.canonicals[key].pk} {self.row(key)['canonical']['match_title']!r}", out)
                self.assertNotIn("warning:", out)
                self.assertFalse(model.objects.exists())
                self.assertIn("Created (draft, unpublished)", self.run_import(key))
                page = self.page(key)
                self.assertFalse(page.live)
                self.assertEqual(page.canonical_id, self.canonicals[key].pk)
                self.assertEqual(page.get_parent().specific, FutureSaintsIndexPage.objects.get(content_kind=model.content_kind))
                self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists(), "never submitted")
                self.assertIn("Verify: 0 differences.", self.run_import(key, "--verify"))
                self.assertIn("Changed: 0", self.run_import(key))

    def test_quick_fact_icons_map_to_sprite_icons(self):
        expected = {
            "lourdes": ["calendar", "marker", "person", "star"],
            "lanciano": ["calendar", "marker", "chalice", "church"],
            "sepulchre": ["marker", "scroll", "calendar", "people"],
            "san_diego": ["number", "calendar", "person", "star", "people"],
        }
        for key, icons in expected.items():
            self.run_import(key)
            facts = list(self.page(key).quick_facts.order_by("sort_order"))
            self.assertEqual([f.icon for f in facts], icons, key)
            self.assertEqual([f.value for f in facts], [q["value"] for q in self.row(key)["quick_facts"]], key)
            self.assertTrue(all(not f.inherit for f in facts), key)


class TypeMappingTests(FourFilesTestCase):
    def test_marian(self):
        self.run_import("lourdes")
        page, ts = self.page("lourdes"), self.row("lourdes")["type_specific"]
        self.assertEqual(page.witnesses, para(ts["who_saw_her"]))
        self.assertEqual(page.message, para(ts["marys_message"]))
        self.assertEqual(page.prayer, para(ts["prayer"]))
        self.assertEqual(page.recognition_note, para(ts["church_recognition"]))

    def test_eucharistic(self):
        self.run_import("lanciano")
        page, ts = self.page("lanciano"), self.row("lanciano")["type_specific"]
        self.assertEqual(page.belief, para(ts["what_catholics_believe"]))
        self.assertEqual(page.reported, para(ts["what_was_reported"]))
        self.assertEqual(page.church_says, para(ts["what_the_church_says"]))
        self.assertEqual(page.evidence_note, para(ts["evidence_note"]))

    def test_holy_land(self):
        self.run_import("sepulchre")
        page, ts = self.page("sepulchre"), self.row("sepulchre")["type_specific"]
        self.assertEqual(page.then_text, para(ts["then"]))
        self.assertEqual(page.now_text, para(ts["now"]))
        self.assertEqual(page.what_we_know, para(ts["what_historians_know"]))
        self.assertEqual(page.tradition, para(ts["what_comes_from_tradition"]))
        self.assertEqual(page.then_and_now, "", "the old field is left alone")
        self.assertEqual(page.people_places, "")
        self.assertEqual(page.story_label, "The Bible Story")
        refs = list(page.bible_references.order_by("sort_order"))
        self.assertEqual([r.citation for r in refs], [b["reference"] for b in ts["bible_references"]], "JSON order, same text")
        self.assertEqual([r.url for r in refs], [b["url"] for b in ts["bible_references"]])
        self.assertEqual((refs[0].book, refs[0].chapter, refs[0].verses), ("Matthew", 27, "33 – 28:10"))

    def test_mission(self):
        self.run_import("san_diego")
        page, row = self.page("san_diego"), self.row("san_diego")
        ts = row["type_specific"]
        self.assertEqual(page.native_peoples, para(ts["native_peoples_and_history"]))
        self.assertEqual(page.mission_life, para(ts["mission_life"]))
        self.assertEqual(page.architecture, para(ts["architecture"]))
        self.assertEqual(page.story_label, "The Mission Story")
        self.assertEqual(page.founding_number, 1)
        self.assertEqual(page.founding_date, date(1769, 7, 16))
        self.assertEqual(page.founding_date_display, row["founding_date_display"])
        self.assertEqual(page.founding_source_note, row["founding_source_note"])
        page.full_clean()                       # the model's rules (1–21, unique) pass

    def test_holy_land_renders_then_now_bible_and_story_heading(self):
        self.run_import("sepulchre")
        page = self.page("sepulchre")
        page.save_revision().publish()          # a test copy only; the importer never publishes
        with FS_ON:
            html = self.html(page.url)
        self.assertIn('<h2 class="fs-tab">The Bible Story</h2>', html)
        self.assertIn("<h3>Then</h3>", html)
        self.assertIn("<h3>Now</h3>", html)
        for ref in self.row("sepulchre")["type_specific"]["bible_references"]:
            self.assertIn(f'<a href="{ref["url"]}" rel="noopener">{ref["reference"]}</a>', html)
        self.assertIn('href="#fs-i-people"', html)
        self.assertIn('href="#then-now"', html, "the third card while People & Places is empty")
        self.assertNotIn('href="#people-places"', html)


class StopTests(FourFilesTestCase):
    def test_type_specific_key_without_a_field_stops(self):
        out = self.failing("lourdes", lambda r: r["type_specific"].update(apparition_count="18"))
        self.assertIn("type_specific: no MarianLearningPage field for key(s) apparition_count", out)

    def test_holy_land_key_on_another_type_stops(self):
        out = self.failing("lanciano", lambda r: r["type_specific"].update(then="Long ago."))
        self.assertIn("no EucharisticLearningPage field for key(s) then", out)

    def test_bible_reference_must_read_back_unchanged(self):
        out = self.failing("sepulchre", lambda r: r["type_specific"]["bible_references"][0].update(reference="Matthew twenty-seven"))
        self.assertIn("isn't \"Book chapter[:verses]\"", out)

    def test_story_label_on_a_type_without_the_field_stops(self):
        out = self.failing("lourdes", lambda r: r.update(story_label="Her Story"))
        self.assertIn("MarianLearningPage has no story label field", out)

    def test_founding_fields_only_on_missions(self):
        out = self.failing("lourdes", lambda r: r.update(founding_number=3))
        self.assertIn('"founding_number" exists only on mission pages', out)

    def test_founding_number_range(self):
        out = self.failing("san_diego", lambda r: r.update(founding_number=22))
        self.assertIn("founding_number must be a whole number from 1 to 21 (got 22)", out)

    def test_founding_number_must_be_unused(self):
        index = FutureSaintsIndexPage.objects.get(content_kind="california_mission")
        index.add_child(instance=MissionLearningPage(title="Another mission", slug="another-mission", founding_number=1))
        out = self.failing("san_diego", lambda r: None)
        self.assertIn("founding_number 1 is already used by", out)

    def test_founding_date_must_be_iso(self):
        out = self.failing("san_diego", lambda r: r.update(founding_date="July 16, 1769"))
        self.assertIn("founding_date must be an ISO date", out)
