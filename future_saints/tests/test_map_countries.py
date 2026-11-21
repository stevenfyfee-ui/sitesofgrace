"""The World Discovery Map's country borders, English country names and "Country:" lines.

Natural Earth, Admin 0 countries, U.S. point of view, 1:10m (v5.1.2), built by
tools/build_world_borders.py. See docs/future-saints/map-calibration.md, "Country borders and names".
The browser checks (sizes, zoom, label collisions on the rendered page, full screen) are in
tools/future_saints_map_countries_screens.py.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from catalog.models import SacredSitePage
from future_saints import countries
from future_saints.countries import country_at, site_country
from future_saints.geo import WORLD_VIEWBOX_HEIGHT, WORLD_VIEWBOX_WIDTH, world_viewbox
from future_saints.models import MarianLearningPage
from future_saints.worldmap import (
    DESKTOP_1X_SCALE,
    LABEL_BANDS,
    PIN_HIT_PX,
    label_box,
    label_data,
    label_may_show,
    label_obstacles,
    place_labels,
    world_labels,
)

from .test_world_map import WorldTestCase

BASE = Path(settings.BASE_DIR)
SVG = BASE / "sitesofgrace" / "static" / "future_saints" / "svg"
CONTROL = {
    "Rome": ((41.9028, 12.4964), "Italy"),
    "Lourdes": ((43.0967, -0.0558), "France"),
    "Fátima": ((39.6317, -8.6724), "Portugal"),
    "Lanciano": ((42.2318, 14.3902), "Italy"),
    "Mexico City": ((19.4326, -99.1332), "Mexico"),
    "Jerusalem": ((31.7784, 35.2296), "Israel"),        # step 0c: the U.S. point of view
    "Amsterdam": ((52.3676, 4.9041), "Netherlands"),
    "Kraków": ((50.0647, 19.9450), "Poland"),
    "Akita": ((39.7186, 140.1024), "Japan"),
    "Kibeho": ((-2.6336, 29.5537), "Rwanda"),
}


def segments(path_d):
    """Every segment of an SVG path made of M/L commands, as frozensets of two points."""
    segs = []
    for chain in path_d.split("M")[1:]:
        pts = [tuple(map(float, p.split(","))) for p in chain.replace("L", " ").split()]
        segs += [frozenset((a, b)) for a, b in zip(pts, pts[1:])]
    return segs


def border_path(name):
    return re.search(r'<path id="fs-world-borders" d="([^"]+)"', (SVG / name).read_text(encoding="utf-8")).group(1)


class CountryDataTests(SimpleTestCase):
    def test_control_cities_fall_in_the_right_country(self):
        for city, ((lat, lng), expected) in CONTROL.items():
            self.assertEqual(country_at(lat, lng), (expected, ""), city)

    def test_no_country_in_the_sea_or_on_a_border(self):
        country, why = country_at(30.0, -40.0)                     # mid-Atlantic
        self.assertEqual(country, "")
        self.assertIn("outside every country", why)
        country, why = country_at(41.9022, 12.4539)                # St. Peter's, 0.1 km from the Vatican's outline
        self.assertEqual(country, "")
        self.assertIn("on the border of", why)

    def test_borders_are_drawn_once_at_both_levels(self):
        for name in ("world-borders.svg", "world-borders-50m.svg"):
            segs = segments(border_path(name))
            self.assertGreater(len(segs), 2000, name)
            self.assertEqual(len(segs), len(set(segs)), f"{name}: a border segment is drawn twice")
            for seg in segs:
                for x, y in seg:
                    self.assertTrue(-1 <= x <= WORLD_VIEWBOX_WIDTH + 1 and -1 <= y <= WORLD_VIEWBOX_HEIGHT + 1, (name, x, y))

    def test_borders_follow_the_us_point_of_view_and_the_folds(self):
        data = json.loads((BASE / "future_saints" / "data" / "world_countries.json").read_text(encoding="utf-8"))
        self.assertIn("point of view: United States", data["source"]["title"])
        self.assertIn("Public domain", data["source"]["licence"])
        # Breakaway and Lease pieces and the UK base areas are folded into their sovereign (SOV_A3).
        self.assertEqual(sorted(data["folded"]), ["B35", "B37", "ESB", "USG", "WSB"])
        # Crimea is Ukraine and Western Sahara is its own shape in this edition.
        self.assertEqual(country_at(44.9521, 34.1024)[0], "Ukraine")
        self.assertEqual(country_at(27.1536, -13.2033)[0], "Western Sahara")
        self.assertEqual(country_at(42.6629, 21.1655)[0], "Kosovo")
        self.assertEqual(country_at(25.0330, 121.5654)[0], "Taiwan")
        self.assertEqual(country_at(31.9038, 35.2034)[0], "Palestine")     # Ramallah
        self.assertEqual(country_at(43.0015, 41.0234)[0], "Georgia")      # Sukhumi (Abkhazia, folded)
        # The UK sovereign base areas are folded into Cyprus (reviewed), so no line is drawn around them.
        self.assertEqual(country_at(34.5880, 32.9860)[0], "Cyprus")       # RAF Akrotiri
        self.assertEqual(country_at(34.9850, 33.7300)[0], "Cyprus")       # Dhekelia
        self.assertNotIn("United Kingdom", {country_at(34.5880, 32.9860)[0], country_at(34.9850, 33.7300)[0]})

    def test_names_are_the_approved_english_names(self):
        names = {lab["name"] for lab in label_data()}
        for shown in ("United States", "China", "Gambia", "Bahamas", "Micronesia", "Vatican City", "United Kingdom",
                      "Democratic Republic of the Congo", "Czech Republic", "Ivory Coast", "East Timor", "Turkey",
                      "Cape Verde", "Republic of the Congo", "Palestine", "Kosovo", "Taiwan", "Western Sahara", "Greenland"):
            self.assertIn(shown, names)
        for never in ("United States of America", "People's Republic of China", "The Gambia", "The Bahamas",
                      "Federated States of Micronesia", "Abkhazia", "South Ossetia", "Guantanamo Bay Naval Base",
                      "Akrotiri Sovereign Base Area", "Dhekelia Cantonment", "Hong Kong", "Puerto Rico",
                      "Scarborough Shoal", "Wake Island"):
            self.assertNotIn(never, names)
        changed = {lab["ne_name"]: lab["name"] for lab in label_data() if lab["ne_name"] != lab["name"]}
        self.assertEqual(changed, {"United States of America": "United States", "People's Republic of China": "China",
                                   "The Gambia": "Gambia", "The Bahamas": "Bahamas",
                                   "Federated States of Micronesia": "Micronesia"})
        self.assertEqual({lab["px"] for lab in label_data()}, {11, 13}, "never smaller than 11px")

    def test_small_countries_wait_for_the_largest_zoom(self):
        by_name = {lab["name"]: lab for lab in label_data()}
        for small in ("Vatican City", "San Marino", "Monaco", "Andorra", "Liechtenstein", "Malta"):
            self.assertIsNone(by_name[small]["fit_scale"], small)
        at_1x = {lab["name"] for lab in label_data() if label_may_show(lab, 1.0, DESKTOP_1X_SCALE)}
        self.assertTrue({"Russia", "Canada", "United States", "Brazil", "China", "Australia"} <= at_1x)
        self.assertLess(len(at_1x), 45, "only large countries at 1x")

    def test_overrides_are_reviewed_and_name_known_countries(self):
        known = countries.country_names()
        for slug, o in countries.overrides().items():
            self.assertIn(o["country"], known, slug)
            self.assertTrue(o["reviewed_on"] and o["why"] and o["site_title"], slug)
        self.assertEqual({slug: o["country"] for slug, o in countries.overrides().items()},
                         {"st-peters-basilica": "Vatican City", "tomb-of-st-john-paul-ii": "Vatican City",
                          "st-peter-s-basilica": "Vatican City", "tomb-of-lazarus": "Palestine"})

    def test_source_and_licence_are_documented(self):
        doc = (BASE / "docs" / "future-saints" / "map-calibration.md").read_text(encoding="utf-8")
        for needed in ("Country borders and names", "ne_10m_admin_0_countries_usa", "5.1.2", "public domain",
                       "pin_country_overrides.json", "build_world_borders.py"):
            self.assertIn(needed, doc)
        for name in ("world-borders.svg", "world-borders-50m.svg"):
            self.assertIn("Public domain", (SVG / name).read_text(encoding="utf-8")[:600])


class LabelPlacementTests(SimpleTestCase):
    """The server's no-JavaScript placement (the browser does the same at the real scale)."""

    pins = [{"pinned": True, "x": x, "y": y, "dx": 0, "dy": 0} for x, y in (world_viewbox(*c) for c, _ in CONTROL.values())]

    def test_no_label_touches_a_pin_the_art_or_another_label(self):
        for band, width in LABEL_BANDS:
            scale = width / WORLD_VIEWBOX_WIDTH
            shown = place_labels(label_data(), self.pins, scale)
            half = PIN_HIT_PX / 2 / scale
            pin_boxes = [(p["x"] - half, p["y"] - half, p["x"] + half, p["y"] + half) for p in self.pins]
            boxes = [label_box(lab, scale) for lab in shown]
            for n, b in enumerate(boxes):
                for other in pin_boxes + label_obstacles() + boxes[n + 1:]:
                    self.assertTrue(b[2] <= other[0] or other[2] <= b[0] or b[3] <= other[1] or other[3] <= b[1],
                                    (band, shown[n]["name"]))

    def test_every_label_gets_its_bands(self):
        # With nothing in the way, the 1x names that fit a phone-width world show there, and on every wider band.
        free = {lab["name"]: lab["bands"] for lab in world_labels([])}
        for name in ("Canada", "China", "Russia"):
            self.assertEqual(free[name], "is-a is-b is-c is-d is-e", name)
        self.assertEqual(free["Brazil"].split()[0], "is-b", "too wide for a 320px world")
        self.assertEqual(free["Vatican City"], "", "never on the static (1x) map")
        # Pins win: Italy's name never sits on Rome or Lanciano.
        pinned = {lab["name"]: lab["bands"] for lab in world_labels(self.pins)}
        self.assertNotIn("is-a", pinned["Italy"])


class CountryPageTests(WorldTestCase):
    def test_card_and_list_show_the_country(self):
        html = self.map_html(story="eucharistic-miracle-of-lanciano")
        card = html.split('id="story-card"')[1].split("</aside>")[0]
        self.assertIn('<p class="fs-world-card-country" data-fs-card-country>Country: Italy</p>', card)
        lst = html.split('id="all-stories"')[1]
        for line in ("Country: Italy", "Country: France", "Country: Israel"):
            self.assertIn(f'<span class="fs-list-meta fs-world-country">{line}</span>', lst)
        self.assertNotIn("Country: United States", lst, "missions stay with the California callout")
        data = json.loads(html.split('id="fs-world-data" type="application/json">')[1].split("</script>")[0])
        self.assertEqual({d["key"]: d["country_line"] for d in data}["church-of-the-holy-sepulchre"], "Country: Israel")

    def test_the_marker_aria_label_uses_the_found_country(self):
        markers = dict(self.markers(self.map_html()))
        self.assertEqual(markers["church-of-the-holy-sepulchre"], "Church of the Holy Sepulchre, Holy Land, Israel")

    def test_a_pin_on_a_border_has_no_country_and_a_staff_warning(self):
        tomb = self.site("Tomb of a Pope (sample)", "tomb-sample", "Marian Apparition", 41.9022, 12.4539, "Vatican City", "Vatican City")
        self.story(MarianLearningPage, "marian_apparition", "tomb-story", "Tomb Story (sample)", tomb)
        html = self.map_html(self.staff, story="tomb-story")
        card = html.split('id="story-card"')[1].split("</aside>")[0]
        self.assertIn("data-fs-card-country hidden>", card)
        self.assertIn("Tomb Story (sample): #", html)
        self.assertIn("no country shown: on the border of", html)

    def test_the_reviewed_override(self):
        basilica = SacredSitePage(title="St. Peter's Basilica", slug="st-peters-basilica", latitude=41.9022, longitude=12.4539)
        self.assertEqual(site_country(basilica), ("Vatican City", ""))
        renamed = SacredSitePage(title="St. Peter's (renamed)", slug="st-peters-basilica", latitude=41.9022, longitude=12.4539)
        country, warning = site_country(renamed)
        self.assertEqual(country, "")
        self.assertIn("is ignored", warning)

    def test_static_map_has_borders_names_and_full_screen_markup(self):
        html = self.map_html()
        art = html.split('<svg class="fs-map-art"')[1].split("</svg>")[0]
        self.assertIn('aria-hidden="true"', html.split('<svg class="fs-map-art"')[1][:200])
        self.assertIn('class="fs-wm-borders" href="/static/future_saints/svg/world-borders.svg#fs-world-borders"', art)
        self.assertIn('data-fs-detail="/static/future_saints/svg/world-borders-50m.svg#fs-world-borders"', art)
        self.assertIn('clip-path="url(#fs-world-land-clip)"', art)
        self.assertRegex(art, r'<text class="fs-wm-label fs-wm-label--big is-b is-c is-d is-e" x="[\d.]+" y="[\d.]+" data-z="1.0" data-s="[\d.]+">Brazil</text>')
        self.assertIn('<div class="fs-wmap-frame">', html)
        self.assertRegex(html, r'<button type="button" class="fs-zoom-button" data-fs-fullscreen hidden aria-label="Show the map full screen">')
        self.assertIn('data-fs-fullscreen-close>Close</button>', html)
        self.assertNotIn("<a ", art, "names and borders are not interactive")

    def test_the_homepage_preview_is_unchanged(self):
        with self.settings(SOG_FUTURE_SAINTS="on"):
            html = self.html("/future-saints/")
        preview = html.split("data-fs-world-preview>")[1].split("</a>")[0]
        self.assertNotIn("fs-wm-borders", preview)
        self.assertNotIn("fs-wm-label", preview)
        self.assertNotIn("data-fs-fullscreen", preview)
