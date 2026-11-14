"""Homepage and index structure: four cards plus a full-width Holy Land card,
reading-level buttons, the menu disclosure, staff-only placeholders, and the
picture rule (a page's own image shows; credits never render; no adult portrait)."""
import datetime
import re

from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from catalog.models import SaintPage
from future_saints.models import WorldMapPage
from home.models import LegalPage

from .base import FS_ON, FS_STAFF, FutureSaintsTestCase


def image(title="Test picture"):
    return get_image_model().objects.create(title=title, file=get_test_image_file())


class HomepageTests(FutureSaintsTestCase):
    def test_four_subject_cards_then_one_full_width_holy_land_card(self):
        with FS_ON:
            html = self.html("/future-saints/")
        row = re.search(r'<ul class="fs-cards fs-cards--four" data-fs-subject-cards>(.*?)</ul>', html, re.S).group(1)
        self.assertEqual(row.count("<li>"), 4)
        self.assertNotIn("Holy Land", row)
        for title in ("Meet the Saints", "Mary &amp; Apparitions", "Eucharistic Miracles", "California Missions"):
            self.assertIn(title, row)
        self.assertEqual(html.count("data-fs-feature"), 1)
        self.assertGreater(html.index("data-fs-feature"), html.index("data-fs-subject-cards"))
        self.assertIn("Explore the Holy Land", html)
        self.assertIn('href="/future-saints/holy-land/"', html)

    def test_brief_text_comes_from_fields(self):
        self.home.headline = "A different headline"
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn("A different headline", html)
        self.assertNotIn("Explore the Wonders of Our Faith!", html)
        self.assertIn("Sites of Grace | Future Saints", html)

    def test_cards_link_only_to_live_indexes(self):
        self.saints.unpublish()
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertNotIn('href="/future-saints/saints/"', html)
        self.assertIn("Meet the Saints", html)

    def test_one_reading_level_on_the_homepage(self):
        with FS_ON:
            html = self.html("/future-saints/").lower()
            ignored = self.html("/future-saints/", level="<script>")
        for marker in ("grades 2", "grades 4", "explorer", "researcher", "choose your adventure",
                       "data-fs-level", "reading level"):
            self.assertNotIn(marker, html)
        # The only form is the search box (PR B); the old reading-level control never comes back.
        forms = re.findall(r"<form[^>]*>", html)
        self.assertEqual(len(forms), 1)
        self.assertIn('role="search"', forms[0])
        self.assertNotIn('name="level"', html)
        self.assertNotIn("<script>", ignored, "an old ?level= link is ignored, never echoed")

    def test_menu_disclosure_markup(self):
        with FS_ON:
            html = self.html("/future-saints/saints/")
        self.assertRegex(html, r'<button type="button" class="fs-menu-button" data-fs-menu-button aria-expanded="false" aria-controls="fs-nav">')
        self.assertIn('<nav id="fs-nav" class="fs-nav" aria-label="Future Saints">', html)
        # Icon-over-label items (comp 03), full labels.
        for label, url in (("Saints", "/future-saints/saints/"), ("Marian Apparitions", "/future-saints/marian-apparitions/"),
                           ("Eucharistic Miracles", "/future-saints/eucharistic-miracles/"), ("Holy Land", "/future-saints/holy-land/"),
                           ("California Missions", "/future-saints/california-missions/")):
            self.assertIn(f'href="{url}"', html)
            self.assertIn(f"<span>{label}</span></a>", html)
        self.assertIn('href="/future-saints/saints/" aria-current="page"', html)
        self.assertIn("Sites of Grace", html.split('class="fs-back-link"', 1)[1][:400])

    def test_map_item_appears_for_everyone_only_once_the_map_is_live(self):
        with FS_STAFF:
            staff = self.html("/future-saints/", self.staff)
        with FS_ON:
            public = self.html("/future-saints/")
        for html in (staff, public):
            self.assertNotIn("/future-saints/map/", html, "the map page is still a draft")
            for marker in ("(coming soon)", "data-fs-phase4", "fs-nav-soon"):
                self.assertNotIn(marker, html)
        self.publish(WorldMapPage.objects.get())
        with FS_ON:
            public = self.html("/future-saints/")
        self.assertIn('href="/future-saints/map/"><svg class="fs-icon fs-nav-icon"', public)
        self.assertIn("<span>Map</span></a>", public)

    def test_breadcrumb(self):
        with FS_ON:
            html = self.html("/future-saints/saints/")
        crumb = re.search(r'aria-label="Breadcrumb">(.*?)</nav>', html, re.S).group(1)
        self.assertRegex(crumb, r'(?s)<a href="/">.*?Home</a>')
        self.assertIn('<a href="/future-saints/">Future Saints</a>', crumb)
        self.assertIn('<li aria-current="page">Saints</li>', crumb)

    def test_index_empty_state_is_staff_only(self):
        with FS_STAFF:
            self.assertIn("Stories are on the way!", self.html("/future-saints/saints/", self.staff))
        with FS_ON:
            self.assertNotIn("Stories are on the way!", self.html("/future-saints/saints/"))


class GrownUpsNoteTests(FutureSaintsTestCase):
    def test_privacy_link_only_when_live_otherwise_staff_chip(self):
        with FS_STAFF:
            html = self.html("/future-saints/", self.staff)
        self.assertNotIn("A note for grown-ups</a>", html)
        self.assertIn("the Privacy Policy isn't live yet", html)
        with FS_ON:
            self.assertNotIn("Privacy Policy isn't live yet", self.html("/future-saints/"))

        privacy = LegalPage(title="Privacy Policy", slug="privacy-policy",
                            effective_date=datetime.date(2026, 1, 1), body="<p>Sample (sample).</p>")
        self.home.get_parent().add_child(instance=privacy)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn('href="/privacy-policy/">A note for grown-ups</a>', html)
        self.assertIn("Back to Sites of Grace", html)
        self.assertIn("Church status information should be checked against official sources.", html)


class PictureRuleTests(FutureSaintsTestCase):
    def test_illustration_shows_without_a_credit(self):
        with FS_ON:
            self.assertIn("fs-art--hero fs-art--placeholder", self.html("/future-saints/"))
        self.home.hero_illustration = image()
        self.home.hero_illustration_alt = "A painted map"
        self.home.full_clean()
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn('alt="A painted map"', html)
        self.assertNotIn("fs-art--hero fs-art--placeholder", html)

    def test_credits_are_never_rendered(self):
        self.home.hero_illustration = image()
        self.home.hero_illustration_credit = "HOME CREDIT NOTE (sample)"
        self.home.card_1_illustration = image("Card")
        self.home.card_1_illustration_credit = "CARD CREDIT NOTE (sample)"
        self.publish(self.home)
        index = self.saints
        index.banner_illustration = image("Banner")
        index.banner_illustration_alt = "A banner"
        index.banner_illustration_credit = "BANNER CREDIT NOTE (sample)"
        self.publish(index)
        with FS_ON:
            pages = [self.html("/future-saints/"), self.html(index.url), self.html(index.url, self.staff)]
        for html in pages:
            self.assertNotIn("CREDIT NOTE", html)
            self.assertNotIn("Pictures:", html)
        self.assertIn('alt="A banner"', pages[1])

    def saint(self, **fields):
        saint = SaintPage(title="St. Test of Example", slug="st-test-of-example", **fields)
        self.home.get_parent().add_child(instance=saint)
        return saint

    def test_saint_of_week_hidden_when_empty(self):
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertNotIn("Saint of the Week", html)

    def test_saint_of_week_never_uses_the_adult_portrait(self):
        saint = self.saint(portrait=image("Portrait"), portrait_credit="Wikimedia Commons, CC BY-SA (sample)")
        self.home.saint_of_week = saint
        self.home.saint_of_week_line = "A line for children (sample)"
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn("Saint of the Week", html)
        self.assertIn("St. Test of Example", html)
        self.assertIn("A line for children (sample)", html)
        self.assertIn("fs-art--portrait fs-art--placeholder", html)
        self.assertNotIn("Portrait of St. Test of Example", html)
        self.assertNotIn("Wikimedia", html)

    def test_saint_of_week_hidden_when_saint_not_live(self):
        saint = self.saint()
        self.home.saint_of_week = saint
        self.publish(self.home)
        saint.unpublish()
        with FS_ON:
            self.assertNotIn("Saint of the Week", self.html("/future-saints/"))

    def test_saint_of_week_spans_the_band_alone_with_no_quiz_to_feature(self):
        saint = self.saint()
        self.home.saint_of_week = saint
        self.publish(self.home)
        with FS_ON:
            public = self.html("/future-saints/")
        with FS_STAFF:
            staff = self.html("/future-saints/", self.staff)
        for html in (public, staff):
            row = re.search(r'<div class="(fs-split[^"]*)" data-fs-saint-row>(.*?)</section>', html, re.S)
            self.assertIn("fs-split--single", row.group(1), "alone (no story has a quiz yet): full band width")
            self.assertIn("St. Test of Example", row.group(2))
            self.assertNotIn("data-fs-quiz-card", html)
            self.assertNotIn("data-fs-phase4", html)
