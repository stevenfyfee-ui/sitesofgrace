"""Phase 2a: the five learning templates.

Switch gating per type, no cookies, banned strings and travel field names,
live (never copied) canonical Quick Facts, uncredited images never shown,
one reading level with no grade labels anywhere, the four cards linking to
sections, index placement rules, quiz validation in the admin form, and the
staff-only Build This Mission slot.
"""
import re

from django.core.exceptions import ValidationError
from django.utils.html import escape
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from catalog.models import PilgrimageTrailPage, SacredSitePage, SaintPage, TrailStop
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.models import (
    EucharisticLearningPage,
    FunFact,
    FutureSaintsIndexPage,
    HolyLandLearningPage,
    MarianLearningPage,
    MissionLearningPage,
    QuickFact,
    QuizChoice,
    QuizQuestion,
    SaintLearningPage,
    TimelineEntry,
    WordToKnow,
)

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase

TRAVEL_FIELDS = (
    "pilgrimage_info", "location_link", "quick_ideal_stay", "quick_best_months", "quick_airport",
    "quick_language", "quick_accessibility", "time_needed", "visit_length", "reservation_required",
    "accessibility_summary", "accessibility_level", "worship_status", "worship_note", "worship_schedule",
    "lodging", "travel_sections", "map_points", "admission",
)
BANNED = ("tp-em.com", "fonts.googleapis", "amazon", "amzn", "affiliate", "booking", "/plan/",
          "newsletter", "sign in", "donate")
# One version of all text for grades 2–5: no grade labels or level controls anywhere.
# (Hyphenated digit pairs aren't checked: they occur in SVG path data.)
GRADE_MARKERS = ("grade", "2–3", "4–5", "explorer", "researcher", "reading level",
                 "data-fs-level", "fs-level", "sessionstorage")


def image(title="Picture"):
    return get_image_model().objects.create(title=title, file=get_test_image_file())


class LearningTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        root = self.home.get_parent()
        self.saint = SaintPage(title="St. Example of Testing", slug="st-example-of-testing",
                               born="Born in a test", died="Died in a test", feast_day="Test feast day")
        root.add_child(instance=self.saint)
        self.sites = {}
        for category in ("Marian Apparition", "Eucharistic Miracle", "Holy Land", "Shrine & Basilica"):
            site = SacredSitePage(title=f"Test {category}", slug=f"test-{category.split()[0].lower()}",
                                  category=category, locality="Testville", country="Testland",
                                  date_display="A test date", canonical_status="Nihil obstat",
                                  pilgrimage_info="<p>SECRET TRAVEL TEXT</p>", location_link="https://example.com/travel")
            root.add_child(instance=site)
            self.sites[category] = site
        # Mission profiles may only link to a page on the California Mission Trail.
        trail = PilgrimageTrailPage(title="Test Mission Trail", slug=MISSION_TRAIL_SLUG)
        trail.stops = [TrailStop(site=self.sites["Shrine & Basilica"], sort_order=0)]
        root.add_child(instance=trail)
        self.pages = {
            "saint": self.make(SaintLearningPage, "saint", self.saint, story_label="his"),
            "marian_apparition": self.make(MarianLearningPage, "marian_apparition", self.sites["Marian Apparition"]),
            "eucharistic_miracle": self.make(EucharisticLearningPage, "eucharistic_miracle", self.sites["Eucharistic Miracle"]),
            "holy_land": self.make(HolyLandLearningPage, "holy_land", self.sites["Holy Land"]),
            "california_mission": self.make(MissionLearningPage, "california_mission", self.sites["Shrine & Basilica"]),
        }

    def make(self, model, kind, canonical, **fields):
        index = FutureSaintsIndexPage.objects.get(content_kind=kind)
        page = model(
            title=f"{canonical.title} profile", slug=f"{canonical.slug}-profile", canonical=canonical,
            student_title=canonical.title, subtitle="A test subtitle",
            intro="<p>Intro text.</p>", story="<p>Story text.</p>",
            think_about_it="A test question?", reflection_question="A test reflection?", **fields,
        )
        inherit = "saint_feast" if model is SaintLearningPage else "site_place"
        page.quick_facts = [QuickFact(icon="calendar", label="Inherited", inherit=inherit),
                            QuickFact(icon="star", label="Typed", value="Typed value")]
        page.timeline = [TimelineEntry(date_display="Step", text="A timeline step")]
        page.fun_facts = [FunFact(text="A fun fact")]
        page.words = [WordToKnow(word="Word", definition="A simple meaning")]
        questions = []
        for n in range(5):
            q = QuizQuestion(prompt=f"Question {n}?", explanation="Because.")
            q.choices = [QuizChoice(text=f"Choice {c}", is_correct=(c == "B")) for c in "ABC"]
            questions.append(q)
        page.quiz_questions = questions
        index.add_child(instance=page)
        page.save_revision().publish()
        return model.objects.get(pk=page.pk)


class GateTests(LearningTestCase):
    def test_switch_for_every_type(self):
        for kind, page in self.pages.items():
            with FS_OFF:
                self.assertEqual(self.get(page.url).status_code, 404, kind)
                self.assertEqual(self.get(page.url, self.staff).status_code, 404, kind)
            with FS_STAFF:
                self.assertEqual(self.get(page.url).status_code, 404, kind)
                response = self.get(page.url, self.staff)
                self.assertEqual(response.status_code, 200, kind)
                self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
            with FS_ON:
                response = self.get(page.url)
                self.assertEqual(response.status_code, 200, kind)
                self.assertNotContains(response, 'name="robots"')

    def test_no_cookies_banned_strings_or_travel_fields(self):
        with FS_ON:
            for kind, page in self.pages.items():
                for params in ({}, {"level": "researcher"}):  # an old ?level= link is simply ignored
                    self.client.cookies.clear()
                    response = self.get(page.url, **params)
                    self.assertEqual(dict(response.cookies), {}, kind)
                    html = response.content.decode().lower()
                    for word in BANNED + TRAVEL_FIELDS:
                        self.assertNotIn(word, html, f"{word!r} on {kind}")
                    self.assertNotIn("secret travel text", html)
                    self.assertNotIn("example.com/travel", html)

    def test_not_in_sitemap_until_on(self):
        with FS_STAFF:
            self.assertNotContains(self.get("/sitemap.xml"), "-profile/")
        with FS_ON:
            self.assertContains(self.get("/sitemap.xml"), "/future-saints/saints/st-example-of-testing-profile/")


class TemplateTests(LearningTestCase):
    def html(self, kind, user=None, **params):
        with FS_ON:
            return super().html(self.pages[kind].url, user, **params)

    def test_four_cards_link_to_sections_on_every_type(self):
        expected = {
            "saint": ["The Story", "Timeline", "Fun Facts", "Quiz"],
            "marian_apparition": ["The Story", "Timeline", "Mary&#x27;s Message", "Quiz"],
            "eucharistic_miracle": ["The Story", "What Happened?", "Why It Matters", "Quiz"],
            "holy_land": ["Bible Story", "Timeline", "People &amp; Places", "Quiz"],
            "california_mission": ["Mission Story", "Timeline", "Native Peoples", "Build &amp; Quiz"],
        }
        for kind in self.pages:
            html = self.html(kind)
            cards = re.findall(r'<a class="fs-lcard" href="#([a-z-]+)">.*?<span class="fs-lcard-title">(.*?)</span>', html, re.S)
            self.assertEqual([t for _, t in cards], expected[kind], kind)
            for anchor, _ in cards:
                self.assertIn(f'id="{anchor}"', html, f"{kind}: #{anchor}")

    def test_heading_is_meet_plus_student_title_on_saints_only(self):
        page = self.pages["saint"]
        page.student_title = "Saint Carlo Acutis"
        page.save_revision().publish()
        html = self.html("saint")
        self.assertIn('<span class="fs-profile-title-text">Meet Saint Carlo Acutis</span>', html)
        self.assertIn("<h1 class=\"fs-ps-title\">Meet Saint Carlo Acutis</h1>", html, "print sheet too")
        for kind in ("marian_apparition", "eucharistic_miracle", "holy_land", "california_mission"):
            title = escape(self.pages[kind].student_title)
            html = self.html(kind)
            self.assertIn(f'<span class="fs-profile-title-text">{title}</span>', html, kind)
            self.assertNotIn(f"Meet {title}", html, kind)

    def test_saint_title_and_story_label(self):
        html = self.html("saint")
        self.assertIn("Meet St. Example of Testing", html)
        self.assertIn('<h2 class="fs-tab">His Story</h2>', html)
        # Other types use student_title.
        self.assertIn("Test Marian Apparition", self.html("marian_apparition"))

    def test_quick_facts_are_read_live_from_canonical(self):
        self.assertIn("Test feast day", self.html("saint"))
        self.assertIn("Testville, Testland", self.html("marian_apparition"))
        self.saint.feast_day = "A changed feast day"
        self.saint.save_revision().publish()
        html = self.html("saint")
        self.assertIn("A changed feast day", html)
        self.assertNotIn("Test feast day", html)
        self.assertFalse(QuickFact.objects.filter(value__icontains="feast").exists(), "never copied into a field")

    def test_church_status_uses_canonical_plain_wording(self):
        self.assertIn("The Church's current judgment:</strong> Devotion permitted", self.html("marian_apparition"))

    def test_one_reading_level_and_no_grade_labels(self):
        for kind in self.pages:
            for params in ({}, {"level": "researcher"}):
                html = self.html(kind, **params).lower()
                for marker in GRADE_MARKERS:
                    self.assertNotIn(marker, html, f"{marker!r} on {kind} {params}")
                self.assertNotIn("<form", html, "no level control (or any form) on learning pages")
        html = self.html("saint")
        self.assertIn("Intro text.", html)
        self.assertIn("Story text.", html)
        self.assertIn("A timeline step", html)
        self.assertIn("A simple meaning", html)

    def test_no_foliage_decoration(self):
        for kind in self.pages:
            self.assertNotIn("foliage", self.html(kind))

    def test_uncredited_images_are_never_rendered(self):
        portrait = image("Canonical portrait")
        self.saint.portrait = portrait
        self.saint.portrait_credit = ""
        self.saint.save_revision().publish()
        page = self.pages["saint"]
        page.hero_illustration = image("Hero")
        page.hero_illustration_alt = "Hero picture"
        page.save_revision().publish()
        html = self.html("saint")
        self.assertNotIn("<img", html.split('<main id="content">', 1)[1])
        self.assertIn("fs-art--profile fs-art--placeholder", html)

        page.hero_illustration_credit = "Painted for Sites of Grace (test)"
        page.save_revision().publish()
        html = self.html("saint")
        self.assertIn('alt="Hero picture"', html)
        self.assertIn("Painted for Sites of Grace (test)", html)

    def test_placeholder_labels_and_build_slot_are_staff_only(self):
        with FS_ON:
            public = FutureSaintsTestCase.html(self, self.pages["california_mission"].url)
            staff = FutureSaintsTestCase.html(self, self.pages["california_mission"].url, self.staff)
        self.assertIn("Art needed: hero portrait (3:4)", staff)
        self.assertIn('id="build"', staff)
        self.assertNotIn("Art needed", public)
        self.assertNotIn('id="build"', public)

    def test_print_sheet_has_the_parts(self):
        html = self.html("saint")
        sheet = html.split('id="fs-print-sheet"', 1)[1]
        for part in ("Quick Facts", "Timeline", "Words to Know", "Five Things I Learned", "Reflect", "fs-ps-lines"):
            self.assertIn(part, sheet)

    def test_quiz_data_and_no_js_fallback(self):
        html = self.html("saint")
        self.assertIn('id="fs-quiz-data"', html)
        self.assertIn("<noscript>", html)
        self.assertEqual(html.count('"correct": true'), 5)

    def test_index_lists_its_child_as_a_card(self):
        with FS_ON:
            html = FutureSaintsTestCase.html(self, "/future-saints/saints/")
        self.assertIn("Meet St. Example of Testing", html)
        self.assertIn("A test subtitle", html)


class PlacementTests(LearningTestCase):
    def test_each_index_takes_only_its_own_type(self):
        saints = FutureSaintsIndexPage.objects.get(content_kind="saint")
        marian = FutureSaintsIndexPage.objects.get(content_kind="marian_apparition")
        self.assertTrue(SaintLearningPage.can_create_at(saints))
        self.assertFalse(SaintLearningPage.can_create_at(marian))
        self.assertTrue(MarianLearningPage.can_create_at(marian))
        self.assertFalse(MissionLearningPage.can_create_at(saints))

    def test_founding_number_range(self):
        page = self.pages["california_mission"]
        page.founding_number = 22
        with self.assertRaises(ValidationError):
            page.full_clean()


class QuizFormTests(LearningTestCase):
    """The admin form: 3–4 choices and exactly one correct on every save;
    exactly five questions to publish."""

    def form(self, questions, publish=False):
        page = self.pages["saint"]
        form_class = SaintLearningPage.get_edit_handler().get_form_class()
        blank = form_class(instance=page, for_user=self.staff, parent_page=page.get_parent())
        data = {}
        for name, field in blank.fields.items():
            value = blank.initial.get(name, field.initial)
            if value in (None, ""):
                continue
            if name in ("intro", "story"):
                continue
            data[name] = value.pk if hasattr(value, "pk") else value
        for prefix, formset in blank.formsets.items():
            data[f"{prefix}-TOTAL_FORMS"] = 0
            data[f"{prefix}-INITIAL_FORMS"] = 0
            data[f"{prefix}-MIN_NUM_FORMS"] = 0
            data[f"{prefix}-MAX_NUM_FORMS"] = 1000
        data["quiz_questions-TOTAL_FORMS"] = len(questions)
        for i, choices in enumerate(questions):
            data[f"quiz_questions-{i}-prompt"] = f"Question {i}?"
            data[f"quiz_questions-{i}-ORDER"] = i
            cp = f"quiz_questions-{i}-choices"
            data.update({f"{cp}-TOTAL_FORMS": len(choices), f"{cp}-INITIAL_FORMS": 0,
                         f"{cp}-MIN_NUM_FORMS": 0, f"{cp}-MAX_NUM_FORMS": 4})
            for j, (text, correct) in enumerate(choices):
                data[f"{cp}-{j}-text"] = text
                data[f"{cp}-{j}-ORDER"] = j
                if correct:
                    data[f"{cp}-{j}-is_correct"] = "on"
        if publish:
            data["action-publish"] = "action-publish"
        return form_class(data, instance=page, for_user=self.staff, parent_page=page.get_parent())

    good = [("A", False), ("B", True), ("C", False)]

    def test_valid_draft_with_fewer_than_five_questions(self):
        form = self.form([self.good, self.good])
        self.assertTrue(form.is_valid(), form.errors)

    def test_two_choices_is_invalid(self):
        form = self.form([[("A", False), ("B", True)]])
        self.assertFalse(form.is_valid())

    def test_no_correct_or_two_correct_is_invalid(self):
        self.assertFalse(self.form([[("A", False), ("B", False), ("C", False)]]).is_valid())
        self.assertFalse(self.form([[("A", True), ("B", True), ("C", False)]]).is_valid())

    def test_publishing_needs_exactly_five_questions(self):
        self.assertFalse(self.form([self.good] * 4, publish=True).is_valid())
        form = self.form([self.good] * 5, publish=True)
        self.assertTrue(form.is_valid(), form.errors)

    def test_quick_fact_must_inherit_a_field_of_its_own_type(self):
        form = self.form([self.good])
        data = form.data.copy()
        data.update({"quick_facts-TOTAL_FORMS": 1, "quick_facts-0-label": "Where", "quick_facts-0-inherit": "site_place",
                     "quick_facts-0-ORDER": 0})
        form = type(form)(data, instance=form.instance, for_user=self.staff, parent_page=form.instance.get_parent())
        self.assertFalse(form.is_valid())
