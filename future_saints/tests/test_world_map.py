"""Phase 4: the World Discovery Map, the homepage map preview and quiz block, and the
scheduled Saint of the Week.

The fixtures mirror production's published stories, with their real coordinates: Our Lady
of Lourdes, the Eucharistic Miracle of Lanciano, the Church of the Holy Sepulchre, Saint
Carlo Acutis (whose one principal site is his shrine in Assisi) and Mission San Diego.
"""
import re
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings

from catalog.models import PilgrimageTrailPage, SacredSitePage, SaintPage, TrailStop
from future_saints.geo import WORLD_VIEWBOX_HEIGHT, WORLD_VIEWBOX_WIDTH, world_viewbox
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.models import (
    EucharisticLearningPage,
    FutureSaintsHomePage,
    FutureSaintsIndexPage,
    HolyLandLearningPage,
    MarianLearningPage,
    MissionLearningPage,
    QuizChoice,
    QuizQuestion,
    SaintLearningPage,
    SaintOfWeekEntry,
    WorldMapPage,
)
from future_saints.worldmap import DESKTOP_MAP_PX, on_land, overlapping, world_items, world_outline

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase

CONTROL = {"Rome": (41.9028, 12.4964), "Lourdes": (43.0967, -0.0558), "Jerusalem": (31.7784, 35.2296),
           "Mexico City": (19.4326, -99.1332), "Fátima": (39.6317, -8.6724)}
BANNED = ("hotel", "booking", "flight", "itinerary", "directions", "travel", "tour", "buy", "shop", "store", "price",
          "amazon", "amzn", "affiliate", "grade", "grades")


def dec(v):
    return Decimal(str(v))


class WorldTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.home.get_parent()
        self.lourdes = self.site("Our Lady of Lourdes", "lourdes", "Marian Apparition", 43.0967, -0.0558, "Lourdes", "France")
        self.lanciano = self.site("Eucharistic Miracle of Lanciano", "lanciano", "Eucharistic Miracle", 42.2306, 14.3903, "Lanciano", "Italy")
        self.sepulchre = self.site("Church of the Holy Sepulchre", "sepulchre", "Holy Land", 31.7784, 35.2296, "Jerusalem", "")
        self.carlo = SaintPage(title="St. Carlo Acutis", slug="st-carlo-acutis")
        self.root.add_child(instance=self.carlo)
        self.shrine = self.site("Shrine of St. Carlo Acutis (Assisi)", "shrine-carlo", "Shrine & Basilica", 43.0707, 12.6196,
                                "Assisi", "Italy", associated_saint=self.carlo)
        self.san_diego = self.site("Mission San Diego de Alcalá", "mission-san-diego", "Shrine & Basilica", 32.784267, -117.106283,
                                   "San Diego", "United States")
        trail = PilgrimageTrailPage(title="California Mission Trail", slug=MISSION_TRAIL_SLUG)
        trail.stops = [TrailStop(site=self.san_diego, sort_order=0)]
        self.root.add_child(instance=trail)
        self.pages = {
            "lourdes": self.story(MarianLearningPage, "marian_apparition", "our-lady-of-lourdes", "Our Lady of Lourdes", self.lourdes),
            "lanciano": self.story(EucharisticLearningPage, "eucharistic_miracle", "eucharistic-miracle-of-lanciano",
                                   "Eucharistic Miracle of Lanciano", self.lanciano),
            "sepulchre": self.story(HolyLandLearningPage, "holy_land", "church-of-the-holy-sepulchre",
                                    "Church of the Holy Sepulchre", self.sepulchre),
            "carlo": self.story(SaintLearningPage, "saint", "carlo-acutis", "Saint Carlo Acutis", self.carlo),
            "san_diego": self.story(MissionLearningPage, "california_mission", "mission-san-diego-de-alcala",
                                    "Mission San Diego de Alcalá", self.san_diego),
        }
        self.world = WorldMapPage.objects.get()
        self.publish(self.world)

    def site(self, title, slug, category, lat, lng, locality, country, **fields):
        site = SacredSitePage(title=title, slug=slug, category=category, latitude=dec(lat), longitude=dec(lng),
                              locality=locality, country=country, **fields)
        self.root.add_child(instance=site)
        return site

    def story(self, model, kind, slug, title, canonical, publish=True, quiz=True):
        index = FutureSaintsIndexPage.objects.get(content_kind=kind)
        page = model(title=title, slug=slug, canonical=canonical, student_title=title, subtitle=f"{title} subtitle (sample)",
                     intro="<p>Intro (sample).</p>", story="<p>Story (sample).</p>")
        if quiz:
            questions = []
            for n in range(5):
                q = QuizQuestion(prompt=f"Question {n} (sample)?", explanation="Because (sample).")
                q.choices = [QuizChoice(text=f"Choice {c}", is_correct=(c == "B")) for c in "ABC"]
                questions.append(q)
            page.quiz_questions = questions
        index.add_child(instance=page)
        if publish:
            page.save_revision().publish()
        else:
            page.unpublish()
        return model.objects.get(pk=page.pk)

    def map_html(self, user=None, **params):
        with FS_ON:
            return self.html(self.world.url, user, **params)

    def items(self):
        return world_items(self.home, None)[0]

    @staticmethod
    def marker_position(html, key):
        """The --x/--y of the marker whose button has value=key."""
        before = html.split(f'value="{key}" class="fs-wm-pin"')[0]
        return re.findall(r"--x: ([\d.]+)%; --y: ([\d.]+)%;", before)[-1]

    def markers(self, html):
        return re.findall(r'<button type="submit" name="story" value="([^"]+)" class="fs-wm-pin"[^>]*aria-label="([^"]+)"', html, re.S)


class AccuracyTests(WorldTestCase):
    def test_outline_is_natural_earth_public_domain_and_documented(self):
        outline = world_outline()
        self.assertEqual(outline["source"]["publisher"], "Natural Earth")
        self.assertIn("Public domain", outline["source"]["licence"])
        self.assertEqual(outline["trimmed_south_of"], -60.0)
        svg = Path(settings.BASE_DIR) / "sitesofgrace" / "static" / "future_saints" / "svg" / "world-outline.svg"
        self.assertIn('id="fs-world-land"', svg.read_text(encoding="utf-8"))
        doc = (Path(settings.BASE_DIR) / "docs" / "future-saints" / "map-calibration.md").read_text(encoding="utf-8")
        for needed in ("World Discovery Map", "Equal Earth", "Natural Earth", "Antarctica"):
            self.assertIn(needed, doc)

    def test_control_cities_are_on_land_in_the_right_order(self):
        pts = {name: world_viewbox(*c) for name, c in CONTROL.items()}
        for name, (x, y) in pts.items():
            self.assertTrue(on_land(x, y), name)
        west_to_east = sorted(pts, key=lambda n: pts[n][0])
        self.assertEqual(west_to_east, ["Mexico City", "Fátima", "Lourdes", "Rome", "Jerusalem"])
        north_to_south = sorted(pts, key=lambda n: pts[n][1])
        self.assertEqual(north_to_south, ["Lourdes", "Rome", "Fátima", "Jerusalem", "Mexico City"])
        self.assertFalse(on_land(*world_viewbox(30, -40)), "the mid-Atlantic is ocean")

    def test_every_pin_is_inside_the_viewbox(self):
        for item in self.items():
            if item["pinned"]:
                self.assertTrue(0 <= item["x"] <= WORLD_VIEWBOX_WIDTH and 0 <= item["y"] <= WORLD_VIEWBOX_HEIGHT, item["title"])

    def test_the_compass_is_in_the_ocean(self):
        for x in range(26, 115, 4):
            for y in range(318, 415, 4):
                self.assertFalse(on_land(x, y), f"compass touches land at ({x}, {y})")

    def test_a_pin_moves_when_its_canonical_coordinates_change(self):
        before = self.marker_position(self.map_html(), "our-lady-of-lourdes")
        self.lourdes.latitude, self.lourdes.longitude = dec(40.0), dec(-3.0)
        self.lourdes.save_revision().publish()
        after = self.marker_position(self.map_html(), "our-lady-of-lourdes")
        x, y = world_viewbox(40.0, -3.0)
        self.assertNotEqual(before, after)
        self.assertEqual(after, (f"{100 * x / 1000:.3f}", f"{100 * y / 445:.3f}"))


class PinRuleTests(WorldTestCase):
    def test_only_published_stories_appear_and_link(self):
        draft = self.story(MarianLearningPage, "marian_apparition", "draft-story", "A Draft Story", self.lourdes, publish=False)
        html = self.map_html()
        self.assertNotIn("A Draft Story", html)
        self.assertNotIn(draft.url_path.split("/home")[-1], html)
        self.assertEqual(len(self.markers(html)), 5, "4 stories + the California callout")

    def test_site_types_use_the_canonical_coordinates_and_aria_label(self):
        labels = dict(self.markers(self.map_html()))
        self.assertEqual(labels["our-lady-of-lourdes"], "Our Lady of Lourdes, Marian apparition, France")
        self.assertEqual(labels["eucharistic-miracle-of-lanciano"], "Eucharistic Miracle of Lanciano, Eucharistic miracle, Italy")
        self.assertEqual(labels["church-of-the-holy-sepulchre"], "Church of the Holy Sepulchre, Holy Land")

    def test_a_site_without_coordinates_is_list_only_with_a_staff_warning(self):
        SacredSitePage.objects.filter(pk=self.sepulchre.pk).update(latitude=None, longitude=None)
        html = self.map_html(self.staff)
        self.assertNotIn('value="church-of-the-holy-sepulchre"', html)
        self.assertIn("Church of the Holy Sepulchre: #", html)
        self.assertIn("has no latitude/longitude, so no pin", html)
        lst = html.split('id="all-stories"')[1]
        self.assertIn("Church of the Holy Sepulchre</a>", lst)
        self.assertIn("Not on the map yet", lst)
        self.assertNotIn("has no latitude/longitude", self.map_html(), "the warning is staff only")

    def test_saint_uses_the_single_principal_site(self):
        html = self.map_html(story="carlo-acutis")
        self.assertIn('value="carlo-acutis"', html)
        self.assertIn("A place connected to Saint Carlo Acutis: Shrine of St. Carlo Acutis (Assisi)", html)
        x, y = world_viewbox(43.0707, 12.6196)
        self.assertIn(f"--x: {100 * x / 1000:.3f}%; --y: {100 * y / 445:.3f}%", html)

    def test_map_place_comes_first(self):
        page = self.pages["carlo"]
        page.map_place = self.lanciano
        page.save_revision().publish()
        self.assertIn("A place connected to Saint Carlo Acutis: Eucharistic Miracle of Lanciano", self.map_html(story="carlo-acutis"))

    def test_two_principal_sites_or_none_means_list_only(self):
        self.site("Second Carlo Site", "carlo-2", "Shrine & Basilica", 45.46, 9.19, "Milan", "Italy", associated_saint=self.carlo)
        html = self.map_html(self.staff)
        self.assertNotIn('value="carlo-acutis"', html)
        self.assertIn("Saint Carlo Acutis: needs a map place (no single principal site", html)
        self.assertIn("Saint Carlo Acutis</a>", html.split('id="all-stories"')[1])
        SacredSitePage.objects.filter(associated_saint=self.carlo).update(associated_saint=None)
        self.assertIn("needs a map place (the saint has no principal site", self.map_html(self.staff))

    def test_one_california_callout_never_21_dots(self):
        self.story(MissionLearningPage, "california_mission", "mission-two", "Mission Two (sample)", self.san_diego)
        html = self.map_html(story="california-missions")
        markers = dict(self.markers(html))
        self.assertEqual([k for k in markers if "mission" in k], ["california-missions"])
        self.assertEqual(markers["california-missions"], "California Missions, 2 mission stories, United States")
        self.assertIn('<span class="fs-wm-count" aria-hidden="true">2</span>', html)
        card = html.split('id="story-card"')[1].split("</aside>")[0]
        self.assertIn('href="/future-saints/california-missions/"', card)
        self.assertIn("Explore the California Missions", card)
        lst = html.split('id="all-stories"')[1]
        self.assertEqual(lst.count("On the map with the California Missions"), 2)

    def test_no_markers_overlap_on_the_desktop_map(self):
        items = self.items()
        self.assertEqual(overlapping(items, DESKTOP_MAP_PX), [], "1440")
        self.assertTrue(any(i["dx"] or i["dy"] for i in items), "the reviewed offsets are in use")
        html = self.map_html()
        self.assertIn('class="fs-wm-marker fs-wm-saint is-offset"', html)
        self.assertIn('<line x1="0" y1="0" x2="0" y2="28"/>', html, "a leader anchors a moved marker to its true spot")


class PageTests(WorldTestCase):
    def test_switch_and_noindex(self):
        with FS_OFF:
            self.assertEqual(self.get(self.world.url, self.staff).status_code, 404)
        with FS_STAFF:
            self.assertEqual(self.get(self.world.url).status_code, 404)
            response = self.get(self.world.url, self.staff)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
        with FS_ON:
            self.assertNotContains(self.get(self.world.url), 'name="robots"')

    def test_filters_story_card_and_list(self):
        html = self.map_html()
        filters = re.findall(r'<button type="button" class="fs-world-filter fs-wm-([a-z_]+)" aria-pressed="true" data-fs-filter="\1">', html)
        self.assertEqual(filters, ["saint", "marian_apparition", "eucharistic_miracle", "holy_land", "california_mission"])
        self.assertIn("data-fs-filter-all>Show all</button>", html)
        self.assertIn("hidden data-fs-world-filters", html, "the toggles appear with JavaScript")
        self.assertIn('data-fs-pin-radius="24"', html)
        self.assertIn('Which story?', html)
        # Markers and list items carry the type the filters hide by.
        self.assertEqual(html.count('class="fs-wm-marker'), 5)
        self.assertEqual(len(re.findall(r'<li data-fs-kind="', html)), 6, "5 stories + the callout")
        # Default card: the first story in the list (types in nav order, then A–Z).
        card = html.split('id="story-card"')[1].split("</aside>")[0]
        self.assertIn("Saint Carlo Acutis", card)
        self.assertIn("Read the Story", card)
        # The list: grouped by type, in nav order.
        groups = re.findall(r'<h3 class="fs-world-group-title">([^<]+)</h3>', html)
        self.assertEqual(groups, ["Saints", "Marian Apparitions", "Eucharistic Miracles", "Holy Land", "California Missions"])

    def test_no_js_selection_and_keyboard_order(self):
        html = self.map_html(story="eucharistic-miracle-of-lanciano")
        self.assertIn('<form class="fs-wmap-pins" method="get" action="#story-card"', html)
        card = html.split('id="story-card"')[1].split("</aside>")[0]
        self.assertIn("Eucharistic Miracle of Lanciano", card)
        self.assertIn("Lanciano, Italy", card)
        pressed = re.findall(r'value="([^"]+)" class="fs-wm-pin"[^>]*aria-pressed="true"', html, re.S)
        self.assertEqual(pressed, ["eucharistic-miracle-of-lanciano"])
        order = [k for k, _ in self.markers(html)]
        self.assertEqual(order, ["carlo-acutis", "our-lady-of-lourdes", "eucharistic-miracle-of-lanciano",
                                 "church-of-the-holy-sepulchre", "california-missions"], "tab order = list order")
        self.assertIn("Saint Carlo Acutis", self.map_html(story="nope").split('id="story-card"')[1][:2000])

    def test_no_banned_words_and_no_geolocation(self):
        for html in (self.map_html(), self.map_html(self.staff)):
            text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S).lower()
            for word in BANNED:
                self.assertIsNone(re.search(rf"\b{word}\b", text), word)
            self.assertNotIn("geolocation", html)
        js = (Path(settings.BASE_DIR) / "sitesofgrace" / "static" / "js" / "future-saints.js").read_text(encoding="utf-8")
        self.assertNotIn("geolocation", js)


class HomepageTests(WorldTestCase):
    def home_html(self, user=None):
        with FS_ON:
            return self.html("/future-saints/", user)

    def test_map_preview_shows_published_pins_and_hides_without_a_live_map(self):
        html = self.home_html()
        preview = html.split("data-fs-world-preview>")[1].split("</a>")[0]
        self.assertIn('href="/future-saints/map/" data-fs-world-preview', html)
        self.assertEqual(preview.count("fs-world-preview-dot"), 5)
        self.assertIn("world-outline.svg#fs-world-land", preview)
        self.assertNotIn("<button", preview, "static, not interactive")
        self.world.refresh_from_db()
        self.world.unpublish()
        self.assertNotIn("data-fs-world-preview", self.home_html())

    def test_quiz_block_featured_then_random_then_hidden(self):
        self.home.quiz_page = self.pages["lanciano"]
        self.publish(self.home)
        html = self.home_html()
        self.assertIn('href="/future-saints/eucharistic-miracles/eucharistic-miracle-of-lanciano/#quiz" data-fs-quiz-card', html)
        self.home.quiz_page = None
        self.publish(self.home)
        self.assertRegex(self.home_html(), r'href="/future-saints/[a-z-]+/[a-z-]+/#quiz" data-fs-quiz-card')
        for page in self.pages.values():
            page.quiz_questions.all().delete()
        self.assertNotIn("data-fs-quiz-card", self.home_html())

    def test_the_quiz_pick_sets_no_cookie(self):
        with FS_ON:
            response = self.get("/future-saints/")
        self.assertEqual(response.cookies, {})


class SaintOfWeekTests(WorldTestCase):
    def schedule(self, *entries):
        self.home.saint_of_week_entries = [SaintOfWeekEntry(week_start=start, saint=self.pages["carlo"], line=line)
                                           for start, line in entries]
        self.publish(self.home)
        self.home = FutureSaintsHomePage.objects.get(pk=self.home.pk)

    def card_at(self, utc):
        with mock.patch("future_saints.models.timezone.now", return_value=utc):
            return self.home.saint_of_week_card(None)

    def test_the_week_containing_today_in_los_angeles(self):
        self.schedule((date(2026, 11, 9), "Last week (sample)"), (date(2026, 11, 16), "This week (sample)"))
        # Monday 16 Nov, 07:30 UTC is still Sunday 15 Nov, 23:30 in Los Angeles: last week's saint.
        self.assertEqual(self.card_at(datetime(2026, 11, 16, 7, 30, tzinfo=dt_timezone.utc))["line"], "Last week (sample)")
        # 08:10 UTC is Monday 00:10 in Los Angeles: the new week.
        self.assertEqual(self.card_at(datetime(2026, 11, 16, 8, 10, tzinfo=dt_timezone.utc))["line"], "This week (sample)")
        # The following Sunday night is still the same week.
        self.assertEqual(self.card_at(datetime(2026, 11, 23, 7, 59, tzinfo=dt_timezone.utc))["line"], "This week (sample)")

    def test_links_to_the_future_saints_page_then_falls_back_then_hides(self):
        self.schedule((date(2026, 11, 16), "Scheduled (sample)"))
        card = self.card_at(datetime(2026, 11, 18, 12, 0, tzinfo=dt_timezone.utc))
        self.assertEqual((card["name"], card["scheduled"]), ("Saint Carlo Acutis", True))
        self.assertTrue(card["url"].endswith("/saints/carlo-acutis/"))
        # No entry this week: the fallback pick, linked to its Future Saints page.
        self.home.saint_of_week, self.home.saint_of_week_line = self.carlo, "Fallback (sample)"
        self.publish(self.home)
        self.home = FutureSaintsHomePage.objects.get(pk=self.home.pk)
        card = self.card_at(datetime(2026, 12, 2, 12, 0, tzinfo=dt_timezone.utc))
        self.assertEqual((card["line"], card["scheduled"]), ("Fallback (sample)", False))
        self.assertTrue(card["url"].endswith("/saints/carlo-acutis/"), "never the adult SaintPage")
        self.home.saint_of_week = None
        self.publish(self.home)
        self.home = FutureSaintsHomePage.objects.get(pk=self.home.pk)
        self.assertIsNone(self.card_at(datetime(2026, 12, 2, 12, 0, tzinfo=dt_timezone.utc)))

    def test_rendered_link_on_the_homepage(self):
        today = datetime.now(dt_timezone.utc)
        from future_saints.models import SAINT_OF_WEEK_TZ
        local = today.astimezone(SAINT_OF_WEEK_TZ).date()
        self.schedule((local - timedelta(days=local.weekday()), "On the homepage (sample)"))
        with FS_ON:
            html = self.html("/future-saints/")
        band = html.split("data-fs-saint>")[1].split("</div>\n      </div>")[0]
        self.assertIn('<a href="/future-saints/saints/carlo-acutis/">Saint Carlo Acutis</a>', band)
        self.assertIn("On the homepage (sample)", band)
        self.assertNotIn("/st-carlo-acutis/", band, "never the adult SaintPage")

    def form(self, *starts):
        form_class = FutureSaintsHomePage.get_edit_handler().get_form_class()
        blank = form_class(instance=self.home, for_user=self.staff, parent_page=self.home.get_parent())
        data = {n: (v.pk if hasattr(v, "pk") else v) for n, f in blank.fields.items()
                if (v := blank.initial.get(n, f.initial)) not in (None, "")}
        for prefix in blank.formsets:
            data.update({f"{prefix}-TOTAL_FORMS": 0, f"{prefix}-INITIAL_FORMS": 0, f"{prefix}-MIN_NUM_FORMS": 0,
                         f"{prefix}-MAX_NUM_FORMS": 1000})
        data["saint_of_week_entries-TOTAL_FORMS"] = len(starts)
        for i, start in enumerate(starts):
            data.update({f"saint_of_week_entries-{i}-week_start": start.isoformat(),
                         f"saint_of_week_entries-{i}-saint": self.pages["carlo"].pk, f"saint_of_week_entries-{i}-ORDER": i})
        return form_class(data, instance=self.home, for_user=self.staff, parent_page=self.home.get_parent())

    def test_admin_validation_monday_and_unique(self):
        ok = self.form(date(2026, 11, 16), date(2026, 11, 23))
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertFalse(self.form(date(2026, 11, 17)).is_valid(), "a Tuesday")
        self.assertFalse(self.form(date(2026, 11, 16), date(2026, 11, 16)).is_valid(), "the same week twice")
