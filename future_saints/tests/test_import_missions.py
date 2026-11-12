"""import_mission_content (Phase 3, step 6): the approved hub text and quiz, the projects
guide and the San Diego project, all as drafts built on each page's latest revision.

Runs on the committed JSON (docs/future-saints/content/missions-hub-and-projects.json),
which was converted from the approved Markdown with no wording changes."""
import copy
import json
import os
import tempfile
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.models import WorkflowState

from future_saints.missions import MissionProjectsGuidePage
from future_saints.models import MissionLearningPage

from .test_missions import MissionsTestCase

CONTENT = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content"
JSON_FILE = CONTENT / "missions-hub-and-projects.json"
MARKDOWN = CONTENT / "future-saints-content-missions-hub-and-projects.md"


class ImportMissionContentTestCase(MissionsTestCase):
    def setUp(self):
        super().setUp()
        self.seed()                                          # the seeded hub missions: a draft revision
        self.hub.refresh_from_db()
        self.mission = MissionLearningPage(title="Mission San Diego de Alcalá", slug="mission-san-diego-de-alcala",
                                           canonical=self.sites[1], student_title="Mission San Diego de Alcalá", live=False)
        self.hub.add_child(instance=self.mission)
        self.mission.save_revision()                         # an unpublished draft, like production #2529
        self.data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
        self.tmp = tempfile.mkdtemp()

    def write(self, data):
        path = os.path.join(self.tmp, "content.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        return path

    def run_import(self, *flags, data=None):
        out = StringIO()
        call_command("import_mission_content", self.write(data or self.importable()), *flags, stdout=out)
        return out.getvalue()

    def failing(self, data, *flags):
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("import_mission_content", self.write(data), *flags, stdout=out)
        return out.getvalue()

    def importable(self):
        """The approved file with the grade line blank, until the owner decides on it."""
        data = copy.deepcopy(self.data)
        data["project"]["grade_note"] = ""
        return data

    def latest(self, page):
        page.refresh_from_db()
        return page.get_latest_revision_as_object()


class FileTests(ImportMissionContentTestCase):
    def test_every_text_value_is_verbatim_from_the_approved_markdown(self):
        plain = MARKDOWN.read_text(encoding="utf-8").replace("**", "")
        structural = {"format", "source", "approved_by", "approved_on", "slug", "status", "model"}
        found = []

        def walk(value, key=""):
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, k)
            elif isinstance(value, list):
                for v in value:
                    walk(v, key)
            elif isinstance(value, str) and value and key not in structural:
                found.append(value)
                self.assertIn(value, plain, f"{key}: not verbatim in the approved file")

        walk(self.data)
        self.assertGreater(len(found), 180)

    def test_the_grade_line_is_held_by_the_no_grade_labels_rule(self):
        out = self.failing(self.data, "--dry-run")
        self.assertIn("grade-level wording isn't allowed (found: Grades 2)", out)
        self.assertFalse(MissionProjectsGuidePage.objects.exists(), "nothing written")


class ImportTests(ImportMissionContentTestCase):
    def test_dry_run_writes_nothing(self):
        revisions = (self.hub.revisions.count(), self.mission.revisions.count())
        out = self.run_import("--dry-run")
        self.assertIn("hub: /home/future-saints/california-missions/", out)
        self.assertIn("quiz 5 questions / 17 choices", out)
        self.assertIn("would create", out)
        self.assertIn("status review_ready; features 4, materials 9, steps 8, fact card rows 7, sources 3", out)
        self.assertIn("Would change: 3", out)
        self.assertFalse(MissionProjectsGuidePage.objects.exists())
        self.assertEqual((self.hub.revisions.count(), self.mission.revisions.count()), revisions)

    def test_import_as_drafts_keeps_the_seeded_missions_then_verifies_and_reruns(self):
        out = self.run_import()
        self.assertIn("Changed: 3 (created 1, new draft revisions 2)", out)
        hub = self.latest(self.hub)
        self.assertEqual(hub.hub_title, "Discover the 21 California Missions")
        self.assertEqual(len(hub.mission_hub_entries.all()), 21, "the seeded missions are kept")
        self.assertEqual([len(q.choices.all()) for q in hub.hub_quiz_questions.all()], [4, 4, 3, 3, 3])
        self.assertTrue(self.hub.has_unpublished_changes)

        guide = MissionProjectsGuidePage.objects.get()
        self.assertFalse(guide.live)
        self.assertEqual(guide.url_path, self.hub.url_path + "projects/")
        self.assertEqual(guide.plan_steps.count(), 5)
        self.assertEqual(guide.safety_items.first().lead, "Grown-ups only:")

        mission = self.latest(self.mission)
        self.assertFalse(self.mission.live)
        project = mission.school_projects.all()[0]
        self.assertEqual(project.status, "review_ready")
        self.assertEqual(project.project_title, "Build This Mission: Mission San Diego de Alcalá")
        self.assertEqual(len(project.steps.all()), 8)
        self.assertEqual(project.model_reference_image_credit, "")
        for page in (self.hub, guide, self.mission):
            self.assertFalse(WorkflowState.objects.filter(object_id=str(page.pk)).exists(), "never submitted")

        self.assertIn("Verify: 0 differences.", self.run_import("--verify"))
        revisions = (self.hub.revisions.count(), self.mission.revisions.count(), guide.revisions.count())
        self.assertIn("Changed: 0", self.run_import())
        self.assertEqual((self.hub.revisions.count(), self.mission.revisions.count(), guide.revisions.count()), revisions)

    def test_verify_finds_a_difference(self):
        self.run_import()
        hub = self.latest(self.hub)
        hub.map_note = "Edited in the admin"
        hub.save_revision()
        out = self.failing(self.importable(), "--verify")
        self.assertIn("map_note: differs", out)


class ValidationTests(ImportMissionContentTestCase):
    def assert_fails(self, change, message):
        data = self.importable()
        change(data)
        self.assertIn(message, self.failing(data, "--dry-run"))

    def test_quiz_rules(self):
        self.assert_fails(lambda d: d["hub"]["quiz"].pop(), "hub.quiz must have exactly 5 questions (it has 4)")
        self.assert_fails(lambda d: d["hub"]["quiz"][0]["choices"].pop(2), "hub.quiz[0] needs exactly one correct choice (it has 0)")

    def test_shopping_words_and_unknown_keys_and_lengths(self):
        self.assert_fails(lambda d: d["guide"]["supplies"].append("Buy glue at a store"), "shopping wording isn't allowed")
        self.assert_fails(lambda d: d["project"].update(mystery="x"), "project: unknown key(s) mystery")
        self.assert_fails(lambda d: d["hub"].update(map_note="x" * 301), "hub.map_note: 301 characters")

    def test_never_imports_a_published_project_or_a_missing_mission(self):
        self.assert_fails(lambda d: d["project"].update(status="published"), 'project.status "published" isn\'t imported')
        self.assert_fails(lambda d: d["project"]["mission"].update(match_title="Mission Nowhere"),
                          "project.mission: 0 live page(s) titled exactly 'Mission Nowhere'")

    def test_source_urls_must_be_https(self):
        self.assert_fails(lambda d: d["project"]["sources"][0].update(url="http://example.com/"), "project.sources[0].url must be a valid https URL")
