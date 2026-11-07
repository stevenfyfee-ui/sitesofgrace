"""Homepage and index structure: four cards plus a full-width Holy Land card,
reading-level buttons, the menu disclosure, staff-only placeholders, and the
picture rule (an image shows only with a credit)."""
import datetime
import re

from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from catalog.models import SaintPage
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

    def test_reading_level_buttons(self):
        with FS_ON:
            html = self.html("/future-saints/")
            pressed = self.html("/future-saints/", level="researcher")
            bogus = self.html("/future-saints/", level="<script>")
        buttons = re.findall(r"<button[^>]*data-fs-level[^>]*>", html)
        self.assertEqual(len(buttons), 2)
        for b in buttons:
            self.assertIn('type="submit"', b)
            self.assertIn('aria-pressed="false"', b)
        self.assertIn('name="level" value="explorer"', html)
        self.assertIn('name="level" value="researcher"', html)
        self.assertIn('method="get"', html)
        self.assertRegex(pressed, r'value="researcher"[^>]*aria-pressed="true"')
        self.assertRegex(pressed, r'value="explorer"[^>]*aria-pressed="false"')
        self.assertNotIn('aria-pressed="true"', bogus)
        self.assertNotIn("<script>", bogus, "an unknown ?level= is ignored, never echoed")

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

    def test_map_item_and_phase4_placeholders_are_staff_only(self):
        with FS_STAFF:
            staff = self.html("/future-saints/", self.staff)
        with FS_ON:
            public = self.html("/future-saints/")
        self.assertIn("(coming soon)", staff)
        self.assertNotIn("/future-saints/map/", staff)
        self.assertIn('data-fs-phase4="map"', staff)
        self.assertIn('data-fs-phase4="quiz"', staff)
        for marker in ("(coming soon)", "data-fs-phase4", "Illustration:", "Staff only"):
            self.assertNotIn(marker, public)

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
    def test_illustration_needs_a_credit(self):
        self.home.hero_illustration = image()
        self.home.hero_illustration_alt = "A painted map"
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertNotIn('alt="A painted map"', html)
        self.assertIn("fs-art--hero fs-art--placeholder", html)

        self.home.hero_illustration_credit = "Painted for Sites of Grace by A. Artist (sample)"
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn('alt="A painted map"', html)
        self.assertNotIn("fs-art--hero fs-art--placeholder", html)
        self.assertIn("Painted for Sites of Grace by A. Artist (sample)", html)

    def saint(self, **fields):
        saint = SaintPage(title="St. Test of Example", slug="st-test-of-example", **fields)
        self.home.get_parent().add_child(instance=saint)
        return saint

    def test_saint_of_week_hidden_when_empty(self):
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertNotIn("Saint of the Week", html)

    def test_saint_portrait_only_with_portrait_credit(self):
        saint = self.saint(portrait=image("Portrait"))
        self.home.saint_of_week = saint
        self.home.saint_of_week_line = "A line for children (sample)"
        self.publish(self.home)
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn("Saint of the Week", html)
        self.assertIn("St. Test of Example", html)
        self.assertIn("A line for children (sample)", html)
        self.assertIn("fs-art--portrait fs-art--placeholder", html)
        self.assertNotIn('alt="Portrait of St. Test of Example"', html)

        saint.portrait_credit = "Public domain (sample)"
        saint.save_revision().publish()
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn('alt="Portrait of St. Test of Example"', html)
        self.assertIn("Public domain (sample)", html)

    def test_saint_of_week_hidden_when_saint_not_live(self):
        saint = self.saint()
        self.home.saint_of_week = saint
        self.publish(self.home)
        saint.unpublish()
        with FS_ON:
            self.assertNotIn("Saint of the Week", self.html("/future-saints/"))
