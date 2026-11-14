"""import_learning_pages: create, update as a new draft revision, skip a page
with a draft, every validation failure, canonical 0/1/many matches, HTML
escaping, idempotency, --dry-run and --verify. Runs on a copy of the approved
Carlo JSON whose canonical match_title points at a fixture saint (Carlo isn't
in the local database). BatchFileTests run content batch 04 unchanged (twelve
pages in one file) against fixture saints titled like the canonical pages."""
import copy
import json
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.models import Revision, WorkflowState

from catalog.models import SaintPage
from future_saints.models import FutureSaintsIndexPage, SaintLearningPage

from .base import FS_ON, FutureSaintsTestCase

APPROVED = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content" / "carlo-acutis.json"
BATCH_04 = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content" / "future-saints-batch-04.json"
FIXTURE_TITLE = "Fixture Saint for Import Tests"


class ImportTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        self.canonical = SaintPage(title=FIXTURE_TITLE, slug="fixture-saint-import", feast_day="Fixture feast day")
        self.home.get_parent().add_child(instance=self.canonical)
        self.data = json.loads(APPROVED.read_text(encoding="utf-8"))
        self.data["pages"][0]["canonical"]["match_title"] = FIXTURE_TITLE
        self.tmp = tempfile.mkdtemp()

    @property
    def row(self):
        return self.data["pages"][0]

    def write(self, data=None):
        path = os.path.join(self.tmp, "pages.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data or self.data, fh, ensure_ascii=False)
        return path

    def run_import(self, *flags, data=None):
        out = StringIO()
        call_command("import_learning_pages", self.write(data), *flags, stdout=out)
        return out.getvalue()

    def failing(self, data, *flags):
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("import_learning_pages", self.write(data), *flags, stdout=out)
        return out.getvalue()

    def page(self):
        return SaintLearningPage.objects.get(slug="carlo-acutis")


class CreateTests(ImportTestCase):
    def test_creates_an_unpublished_draft_with_everything_mapped(self):
        out = self.run_import()
        self.assertIn("Created (draft, unpublished)", out)
        page = self.page()
        self.assertFalse(page.live)
        self.assertEqual(page.get_parent().specific, FutureSaintsIndexPage.objects.get(content_kind="saint"))
        self.assertEqual(Revision.page_revisions.filter(object_id=str(page.pk)).count(), 1)
        self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists(), "never submitted to the workflow")
        self.assertEqual(page.canonical_id, self.canonical.pk)
        self.assertEqual(page.title, "Saint Carlo Acutis")
        self.assertEqual(page.student_title, "Saint Carlo Acutis")
        self.assertEqual(page.story_label, "his")
        self.assertEqual(page.story.count("<p>"), 7)
        self.assertTrue(page.intro.startswith("<p>Carlo Acutis was an Italian teenager"))
        self.assertEqual(page.kindness_prompt, self.row["kindness_prompt"])
        facts = list(page.quick_facts.order_by("sort_order"))
        self.assertEqual([(f.icon, f.label, f.inherit, f.value) for f in facts], [
            ("calendar", "Lived", "saint_lived", "1991–2006"),
            ("marker", "From", "", "Milan, Italy (born in London, England)"),
            ("feast", "Feast Day", "saint_feast", "October 12"),
            ("chalice", "Known for", "", "Love of the Eucharist"),
        ])
        self.assertEqual([t.sort_order for t in page.timeline.order_by("sort_order")], list(range(8)))
        self.assertEqual(page.timeline.order_by("sort_order").first().date_display, "May 3, 1991")
        self.assertEqual(page.fun_facts.count(), 6)
        self.assertEqual(page.words.count(), 5)
        self.assertEqual(page.sources.count(), 6)
        questions = list(page.quiz_questions.order_by("sort_order"))
        self.assertEqual(len(questions), 5)
        first = list(questions[0].choices.order_by("sort_order"))
        self.assertEqual([c.text for c in first], ["Rome, Italy", "London, England", "Assisi, Italy", "Paris, France"])
        self.assertEqual([c.is_correct for c in first], [False, True, False, False])

    def test_dry_run_writes_nothing(self):
        out = self.run_import("--dry-run")
        self.assertIn("Would create (draft)", out)
        self.assertIn(f"canonical: #{self.canonical.pk} '{FIXTURE_TITLE}'", out)
        self.assertIn("production_id_hint 2247: differs", out)
        self.assertIn("quiz 5 questions / 18 choices", out)
        self.assertIn("'Lived' inherits saint_lived: shows '1991–2006' (fallback_value; canonical field empty)", out)
        self.assertIn("'Feast Day' inherits saint_feast: shows 'Fixture feast day' (from the canonical page)", out)
        self.assertFalse(SaintLearningPage.objects.filter(slug="carlo-acutis").exists())

    def test_second_run_with_unchanged_json_changes_nothing(self):
        self.run_import()
        revisions = Revision.page_revisions.filter(object_id=str(self.page().pk)).count()
        out = self.run_import()
        self.assertIn("Changed: 0", out)
        self.assertIn("unchanged 1", out)
        self.assertEqual(Revision.page_revisions.filter(object_id=str(self.page().pk)).count(), revisions)

    def test_verify_reports_zero_then_finds_a_difference(self):
        self.run_import()
        self.assertIn("Verify: 0 differences.", self.run_import("--verify"))
        page = self.page()
        page.subtitle = "Edited in the admin"
        page.save_revision()
        out = self.failing(self.data, "--verify")
        self.assertIn("1 difference(s)", out)
        self.assertIn("subtitle: differs", out)

    def test_text_is_escaped_never_html(self):
        data = copy.deepcopy(self.data)
        data["pages"][0]["story_paragraphs"][0] = 'He wrote <b>bold</b> & <script>alert("x")</script> here.'
        self.run_import(data=data)
        story = self.page().story
        self.assertIn("&lt;b&gt;bold&lt;/b&gt; &amp; &lt;script&gt;", story)
        self.assertNotIn("<script>", story)
        self.assertNotIn("<b>", story)


class UpdateAndSkipTests(ImportTestCase):
    def test_existing_page_without_a_draft_gets_a_new_draft_revision(self):
        self.run_import()
        page = self.page()
        page.save_revision().publish()          # an editor published it
        page.refresh_from_db()
        self.assertFalse(page.has_unpublished_changes)
        data = copy.deepcopy(self.data)
        data["pages"][0]["subtitle"] = "A changed subtitle for the test."
        out = self.run_import(data=data)
        self.assertIn("Updated (new draft revision)", out)
        page.refresh_from_db()
        self.assertTrue(page.live)
        self.assertTrue(page.has_unpublished_changes, "saved as a draft, not published")
        self.assertEqual(page.subtitle, self.row["subtitle"], "the live page is untouched")
        self.assertEqual(page.get_latest_revision_as_object().subtitle, "A changed subtitle for the test.")

    def test_existing_page_with_a_draft_is_skipped(self):
        self.run_import()               # created unpublished: it is a draft
        before = Revision.page_revisions.filter(object_id=str(self.page().pk)).count()
        data = copy.deepcopy(self.data)
        data["pages"][0]["subtitle"] = "A changed subtitle for the test."
        out = self.run_import(data=data)
        self.assertIn("Skipped", out)
        self.assertIn("unpublished draft", out)
        self.assertEqual(Revision.page_revisions.filter(object_id=str(self.page().pk)).count(), before)


class ValidationTests(ImportTestCase):
    def variant(self, change):
        data = copy.deepcopy(self.data)
        change(data["pages"][0])
        return data

    def assert_fails(self, change, message):
        out = self.failing(self.variant(change))
        self.assertIn(message, out)
        self.assertFalse(SaintLearningPage.objects.filter(slug="carlo-acutis").exists(), "nothing written")

    def test_quiz_needs_exactly_five_questions(self):
        self.assert_fails(lambda r: r["quiz"].pop(), "quiz must have exactly 5 questions (it has 4)")

    def test_question_needs_three_or_four_choices(self):
        self.assert_fails(lambda r: r["quiz"][1]["choices"].pop(), "quiz[1] needs 3 or 4 choices (it has 2)")

    def test_question_needs_exactly_one_correct(self):
        self.assert_fails(lambda r: r["quiz"][0]["choices"][1].pop("correct"), "quiz[0] needs exactly one correct choice (it has 0)")
        self.assert_fails(lambda r: r["quiz"][0]["choices"][0].update(correct=True), "quiz[0] needs exactly one correct choice (it has 2)")

    def test_sources_must_be_https(self):
        self.assert_fails(lambda r: r["sources"][0].update(url="http://example.com/x"), "sources[0].url must be a valid https URL")

    def test_too_long_text_is_rejected_not_truncated(self):
        self.assert_fails(lambda r: r["fun_facts"].__setitem__(0, "x" * 300), "fun_facts[0]: 300 characters, but FunFact.text allows 255")

    def test_grade_level_wording_is_rejected(self):
        self.assert_fails(lambda r: r.update(subtitle="For Grades 2–5 readers."), "grade-level wording isn't allowed")

    def test_unknown_keys_are_not_dropped_silently(self):
        self.assert_fails(lambda r: r.update(mystery="x"), "unknown key(s): mystery")

    def test_unknown_inherit_and_icon_fail(self):
        self.assert_fails(lambda r: r["quick_facts"][0].update(inherit="place"), "inherit 'place' isn't available for SaintLearningPage")
        self.assert_fails(lambda r: r["quick_facts"][0].update(icon="rocket"), "icon 'rocket' isn't one of the model's icons")

    def test_story_label_must_be_known(self):
        self.assert_fails(lambda r: r.update(story_label="Their Tale"), "story_label 'Their Tale' must be one of")

    def test_warnings_for_lengths_do_not_fail(self):
        data = self.variant(lambda r: r.update(intro="Short intro."))
        out = self.run_import("--dry-run", data=data)
        self.assertIn("warning: intro is 2 words (target 50–80)", out)


class CanonicalMatchTests(ImportTestCase):
    def test_no_live_match_fails(self):
        self.canonical.unpublish()
        out = self.failing(self.data)
        self.assertIn(f"0 live catalog.SaintPage page(s) titled exactly '{FIXTURE_TITLE}'", out)

    def test_two_matches_fail(self):
        twin = SaintPage(title=FIXTURE_TITLE, slug="fixture-saint-import-twin")
        self.home.get_parent().add_child(instance=twin)
        out = self.failing(self.data)
        self.assertIn(f"2 live catalog.SaintPage page(s) titled exactly '{FIXTURE_TITLE}'", out)

    def test_exactly_one_match_links_by_object_not_hint(self):
        self.run_import()
        self.assertEqual(self.page().canonical_id, self.canonical.pk)
        self.assertNotEqual(self.canonical.pk, 2247)


class RenderingTests(ImportTestCase):
    def test_fallback_label_and_kindness_render(self):
        self.run_import()
        page = self.page()
        page.save_revision().publish()
        with FS_ON:
            html = self.html(page.url)
        self.assertIn('<span class="fs-profile-title-text">Meet Saint Carlo Acutis</span>', html, "comp 03 heading")
        self.assertIn('<h2 class="fs-tab">His Story</h2>', html)
        self.assertIn("1991–2006", html, "fallback shown: the fixture saint has no born/died")
        self.assertIn("Fixture feast day", html, "canonical value wins over the fallback")
        self.assertNotIn("October 12", html.split('id="fs-print-sheet"')[0].split("Quick Facts")[1].split("</aside>")[0])
        self.assertLess(html.index('id="reflection"'), html.index('id="kindness"'))
        self.assertIn("Try a small act of kindness", html)


class BatchFileTests(FutureSaintsTestCase):
    """One file, many pages: every page is planned and written on its own."""
    NOTE = "Imported from content batch 04 on 2026-11-12. Text review by Steven pending."

    def setUp(self):
        super().setUp()
        self.data = json.loads(BATCH_04.read_text(encoding="utf-8"))
        for i, row in enumerate(self.data["pages"]):
            title = row["canonical"]["match_title"]
            self.home.get_parent().add_child(instance=SaintPage(title=title, slug=f"fixture-batch-saint-{i}"))

    def run_import(self, *flags):
        out = StringIO()
        call_command("import_learning_pages", str(BATCH_04), *flags, stdout=out)
        return out.getvalue()

    def test_every_page_in_the_file_becomes_a_draft_with_the_review_note(self):
        out = self.run_import("--review-note", self.NOTE)
        self.assertIn("Changed: 12 (created 12, updated 0); unchanged 0; skipped 0; failed 0.", out)
        slugs = [row["slug"] for row in self.data["pages"]]
        pages = {p.slug: p for p in SaintLearningPage.objects.filter(slug__in=slugs)}
        self.assertEqual(sorted(pages), sorted(slugs))
        for slug, page in pages.items():
            self.assertFalse(page.live, slug)
            self.assertEqual(page.review_note, self.NOTE, slug)
            self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists(), slug)
        self.assertIn("Verify: 0 differences.", self.run_import("--verify", "--review-note", self.NOTE))
        self.assertIn("unchanged 12", self.run_import("--review-note", self.NOTE))

    def test_a_source_note_longer_than_255_characters_imports_unchanged(self):
        row = next(r for r in self.data["pages"] if r["slug"] == "joachim-and-anne")
        self.assertGreater(len(row["sources"][0]["note"]), 255)
        self.run_import()
        page = SaintLearningPage.objects.get(slug="joachim-and-anne")
        self.assertEqual(page.sources.order_by("sort_order").first().note, row["sources"][0]["note"])

    def test_without_review_note_the_field_is_left_alone(self):
        self.run_import("--review-note", self.NOTE)
        out = self.run_import()
        self.assertIn("unchanged 12", out)
        self.assertEqual(SaintLearningPage.objects.get(slug="peter").review_note, self.NOTE)

    def test_review_note_is_never_shown(self):
        self.run_import("--review-note", self.NOTE)
        page = SaintLearningPage.objects.get(slug="peter")
        page.save_revision().publish()
        with FS_ON:
            html = self.html(page.url)
        self.assertNotIn("Text review by Steven pending", html)

    def test_quick_facts_render_the_labels_the_file_gives(self):
        self.run_import()
        rows = {}
        for slug in ("michael-the-archangel", "joachim-and-anne"):
            page = SaintLearningPage.objects.get(slug=slug)
            page.save_revision().publish()
            rows[slug] = page
        with FS_ON:
            michael = self.html(rows["michael-the-archangel"].url)
            joachim = self.html(rows["joachim-and-anne"].url)
        card = lambda html: html.split('id="fs-qf-title"')[1].split("</aside>")[0]
        self.assertIn("Who:</dt>", card(michael))
        self.assertIn("In the Bible:</dt>", card(michael))
        self.assertIn("The books of Daniel and Revelation", card(michael))
        self.assertIn("September 29", card(michael), "inherited feast day falls back: the fixture has none")
        self.assertNotIn("Lived:</dt>", card(michael))
        self.assertIn("Lived:</dt>", card(joachim))
        self.assertIn("Before the birth of Jesus", card(joachim))
        self.assertIn("Nazareth, according to tradition", card(joachim))

    def test_review_note_too_long_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_import("--dry-run", "--review-note", "x" * 256)
