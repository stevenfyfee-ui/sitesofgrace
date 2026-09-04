"""Tests for pilgrimage trails.

Three things carry the whole feature and are what these tests protect:
the ORDER of the stops (a route whose stops shuffle is not a route), the
split between a page-backed stop and a bare waypoint, and the importer's
promise that a re-run never overwrites narrative someone has edited.
"""

import io
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from catalog.models import PilgrimageTrailPage, SacredSitePage, TrailStop
from home.models import StandardPage


class TrailTestCase(WagtailPageTestCase):
    def site_root(self):
        return Site.objects.get(is_default_site=True).root_page

    def make_site(self, slug, title="A Site", **kwargs):
        page = SacredSitePage(
            title=title,
            slug=slug,
            category="Shrine & Basilica",
            latitude=Decimal(kwargs.pop("latitude", "34.000000")),
            longitude=Decimal(kwargs.pop("longitude", "-118.000000")),
            **kwargs,
        )
        self.site_root().add_child(instance=page)
        return SacredSitePage.objects.get(pk=page.pk)

    def make_trail(self, slug="a-trail", title="A Trail", **kwargs):
        page = PilgrimageTrailPage(title=title, slug=slug, **kwargs)
        self.site_root().add_child(instance=page)
        return PilgrimageTrailPage.objects.get(pk=page.pk)

    def run_import(self, *args):
        """stdout swallowed -- the command's summary is written for a human at
        a terminal, and it drowns the test log."""
        call_command("import_trails", *args, verbosity=0, stdout=io.StringIO())

    def add_stop(self, trail, order, site=None, name="", lat=None, lng=None, **kwargs):
        return TrailStop.objects.create(
            trail=trail,
            sort_order=order,
            site=site,
            waypoint_name=name,
            waypoint_latitude=None if lat is None else Decimal(lat),
            waypoint_longitude=None if lng is None else Decimal(lng),
            **kwargs,
        )


class StopOrderTests(TrailTestCase):
    def test_stops_are_numbered_in_route_order_not_creation_order(self):
        """The order of the stops IS the content of a trail.

        Numbers come from sort_order, so a stop inserted in the middle
        renumbers everything after it rather than being appended as the last
        number.
        """
        trail = self.make_trail()
        self.add_stop(trail, 2, name="Third", lat="3.0", lng="3.0")
        self.add_stop(trail, 0, name="First", lat="1.0", lng="1.0")
        self.add_stop(trail, 1, name="Second", lat="2.0", lng="2.0")

        trail = PilgrimageTrailPage.objects.get(pk=trail.pk)
        self.assertEqual(
            [(s.stop_number, s.display_title) for s in trail.stops_for_display],
            [(1, "First"), (2, "Second"), (3, "Third")],
        )

    def test_a_stop_without_coordinates_is_listed_but_not_mapped(self):
        """A half-filled stop must shorten the line, never break the map."""
        trail = self.make_trail()
        self.add_stop(trail, 0, name="Mapped", lat="1.0", lng="1.0")
        self.add_stop(trail, 1, name="No coordinates yet")
        self.add_stop(trail, 2, name="Also mapped", lat="2.0", lng="2.0")

        trail = PilgrimageTrailPage.objects.get(pk=trail.pk)
        self.assertEqual(len(trail.stops_for_display), 3)
        self.assertEqual([s.display_title for s in trail.mapped_stops],
                         ["Mapped", "Also mapped"])
        self.assertTrue(trail.has_map)

    def test_one_mapped_stop_is_not_a_map(self):
        trail = self.make_trail()
        self.add_stop(trail, 0, name="Only one", lat="1.0", lng="1.0")
        self.assertFalse(PilgrimageTrailPage.objects.get(pk=trail.pk).has_map)


class WaypointVersusPageTests(TrailTestCase):
    def test_a_page_backed_stop_takes_its_name_and_coordinates_from_the_page(self):
        """Promoting a waypoint is one field change; the typed values stop
        being used the moment a page is chosen, so they cannot drift."""
        site = self.make_site("burgos", title="Burgos Cathedral",
                              locality="Burgos", country="Spain",
                              latitude="42.340806", longitude="-3.704472")
        trail = self.make_trail()
        stop = self.add_stop(
            trail, 0, site=site,
            name="Stale typed name", lat="0.0", lng="0.0",
        )

        stop = TrailStop.objects.get(pk=stop.pk)
        self.assertEqual(stop.display_title, "Burgos Cathedral")
        self.assertEqual(stop.display_locality, "Burgos, Spain")
        self.assertEqual(stop.latitude, Decimal("42.340806"))
        self.assertEqual(stop.url, site.url)

    def test_a_waypoint_has_no_url(self):
        """A waypoint must not render as a dead link."""
        trail = self.make_trail()
        stop = self.add_stop(trail, 0, name="Pamplona", lat="42.8", lng="-1.6")
        self.assertEqual(stop.url, "")

    def test_an_unpublished_stop_page_has_no_url_either(self):
        site = self.make_site("draft-site", live=False)
        trail = self.make_trail()
        stop = self.add_stop(trail, 0, site=site)
        self.assertEqual(TrailStop.objects.get(pk=stop.pk).url, "")

    def test_a_stop_needs_a_page_or_a_name(self):
        from django.core.exceptions import ValidationError

        trail = self.make_trail()
        with self.assertRaises(ValidationError):
            TrailStop(trail=trail, sort_order=0).clean()


class SitePagePositionTests(TrailTestCase):
    def test_a_site_knows_where_it_sits_and_who_its_neighbours_are(self):
        first = self.make_site("first", title="First")
        middle = self.make_site("middle", title="Middle")
        last = self.make_site("last", title="Last")
        trail = self.make_trail(title="The Trail")
        self.add_stop(trail, 0, site=first)
        self.add_stop(trail, 1, site=middle)
        self.add_stop(trail, 2, site=last)

        position = SacredSitePage.objects.get(pk=middle.pk).trail_positions[0]
        self.assertEqual(position["number"], 2)
        self.assertEqual(position["total"], 3)
        self.assertEqual(position["previous"].display_title, "First")
        self.assertEqual(position["next"].display_title, "Last")

    def test_the_ends_of_a_trail_have_only_one_neighbour(self):
        first = self.make_site("first", title="First")
        last = self.make_site("last", title="Last")
        trail = self.make_trail()
        self.add_stop(trail, 0, site=first)
        self.add_stop(trail, 1, site=last)

        start = SacredSitePage.objects.get(pk=first.pk).trail_positions[0]
        self.assertIsNone(start["previous"])
        self.assertEqual(start["next"].display_title, "Last")

    def test_a_site_can_sit_on_more_than_one_trail(self):
        site = self.make_site("shared", title="Shared")
        for index, slug in enumerate(["trail-a", "trail-b"]):
            trail = self.make_trail(slug=slug, title=f"Trail {slug[-1].upper()}")
            self.add_stop(trail, 0, site=site)

        positions = SacredSitePage.objects.get(pk=site.pk).trail_positions
        self.assertEqual([p["trail"].slug for p in positions], ["trail-a", "trail-b"])

    def test_an_unpublished_trail_does_not_claim_its_sites(self):
        """A draft trail must not put a band on a live site page."""
        site = self.make_site("quiet")
        trail = self.make_trail(live=False)
        self.add_stop(trail, 0, site=site)
        self.assertEqual(SacredSitePage.objects.get(pk=site.pk).trail_positions, [])

    def test_the_band_renders_on_the_site_page(self):
        first = self.make_site("first", title="First", the_story="<p>Story.</p>")
        second = self.make_site("second", title="Second")
        trail = self.make_trail(title="The Camino")
        self.add_stop(trail, 0, site=first)
        self.add_stop(trail, 1, site=second)

        html = self.client.get(first.url).content.decode()
        self.assertIn("Stop 1 of 2", html)
        self.assertIn("The Camino", html)
        self.assertIn("Second", html)


class TrailPageRenderTests(TrailTestCase):
    def test_the_page_renders_its_stops_in_order(self):
        trail = self.make_trail(
            title="The Mission Trail",
            summary_short="Twenty-one missions.",
            the_story="<p>Story.</p>",
        )
        site = self.make_site("first-mission", title="First Mission")
        self.add_stop(trail, 0, site=site, note="Where it starts.")
        self.add_stop(trail, 1, name="A waypoint", lat="35.0", lng="-120.0")

        html = self.client.get(trail.url).content.decode()
        self.assertIn("First Mission", html)
        self.assertIn("Where it starts.", html)
        self.assertIn("A waypoint", html)
        self.assertIn('id="stops"', html)
        self.assertIn('id="the-route"', html)
        self.assertLess(html.index("First Mission"), html.index("A waypoint"))

    def test_the_rail_lists_the_route_the_narrative_and_the_stops(self):
        trail = self.make_trail(the_story="<p>Story.</p>", go_deeper="<p>More.</p>")
        self.add_stop(trail, 0, name="One", lat="1.0", lng="1.0")
        self.add_stop(trail, 1, name="Two", lat="2.0", lng="2.0")

        trail = PilgrimageTrailPage.objects.get(pk=trail.pk)
        self.assertEqual(
            [item["id"] for item in trail.section_nav],
            ["the-route", "the-story", "stops", "go-deeper"],
        )

    def test_the_quick_card_needs_two_facts(self):
        """Same rule as a site page -- one fact reads as broken."""
        trail = self.make_trail(length_display="600 miles")
        self.assertFalse(trail.show_quick_card)
        trail.duration_display = "1-2 weeks"
        self.assertFalse(PilgrimageTrailPage(
            length_display="600 miles").show_quick_card)
        full = self.make_trail(slug="full", length_display="600 miles",
                               duration_display="1-2 weeks")
        self.assertTrue(full.show_quick_card)


class TrailsJsonTests(TrailTestCase):
    def test_the_payload_carries_the_stops_in_order_with_the_line_color(self):
        trail = self.make_trail(title="The Camino", line_color="navy")
        self.add_stop(trail, 0, name="Start", lat="1.0", lng="1.0")
        self.add_stop(trail, 1, name="End", lat="2.0", lng="2.0")

        data = json.loads(self.client.get(reverse("pilgrimage_trails_json")).content)
        self.assertEqual(len(data["trails"]), 1)
        payload = data["trails"][0]
        self.assertEqual(payload["color"], "#032553")
        self.assertEqual([s["title"] for s in payload["stops"]], ["Start", "End"])
        self.assertEqual([s["number"] for s in payload["stops"]], [1, 2])

    def test_a_trail_with_nothing_to_draw_is_left_out(self):
        trail = self.make_trail()
        self.add_stop(trail, 0, name="Lonely", lat="1.0", lng="1.0")

        data = json.loads(self.client.get(reverse("pilgrimage_trails_json")).content)
        self.assertEqual(data["trails"], [])

    def test_an_unpublished_trail_is_left_out(self):
        trail = self.make_trail(live=False)
        self.add_stop(trail, 0, name="One", lat="1.0", lng="1.0")
        self.add_stop(trail, 1, name="Two", lat="2.0", lng="2.0")

        data = json.loads(self.client.get(reverse("pilgrimage_trails_json")).content)
        self.assertEqual(data["trails"], [])

    def test_the_trail_filter_narrows_to_one_route(self):
        for slug in ["trail-a", "trail-b"]:
            trail = self.make_trail(slug=slug, title=slug)
            self.add_stop(trail, 0, name="One", lat="1.0", lng="1.0")
            self.add_stop(trail, 1, name="Two", lat="2.0", lng="2.0")

        url = reverse("pilgrimage_trails_json") + "?trail=trail-b"
        data = json.loads(self.client.get(url).content)
        self.assertEqual([t["slug"] for t in data["trails"]], ["trail-b"])


class ImportTrailsTests(TrailTestCase):
    """The importer's contract: additive, and never destructive by default."""

    def setUp(self):
        super().setUp()
        root = self.site_root()
        for slug, title in [
            ("shrines-and-basilicas", "Shrines & Basilicas"),
            ("pilgrimage-routes", "Pilgrimage Routes"),
        ]:
            page = StandardPage(title=title, slug=slug)
            root.add_child(instance=page)

    def write(self, payload):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(payload, handle)
        handle.close()
        return handle.name

    def payload(self, story="Imported story."):
        return {
            "sites": [{
                "slug": "test-mission",
                "title": "Test Mission",
                "category": "Shrine & Basilica",
                "locality": "Somewhere, California",
                "country": "United States",
                "latitude": 34.0,
                "longitude": -118.0,
                "summary_short": "A mission.",
                "the_story": story,
            }],
            "trail": {
                "slug": "test-trail",
                "title": "Test Trail",
                "trail_type": "Driving route",
                "line_color": "terracotta",
                "stops": [
                    {"site": "test-mission", "note": "First."},
                    {"name": "A waypoint", "latitude": 35.0, "longitude": -119.0},
                ],
            },
        }

    def test_a_full_import_builds_the_pages_the_trail_and_the_stops(self):
        self.run_import(self.write(self.payload()))

        site = SacredSitePage.objects.get(slug="test-mission")
        self.assertEqual(site.get_parent().slug, "shrines-and-basilicas")
        self.assertIn("Imported story.", site.the_story)

        trail = PilgrimageTrailPage.objects.get(slug="test-trail")
        self.assertEqual(trail.get_parent().slug, "pilgrimage-routes")
        self.assertEqual(trail.line_hex, "#A65A3A")
        self.assertEqual(
            [s.display_title for s in trail.stops_for_display],
            ["Test Mission", "A waypoint"],
        )

    def test_paragraphs_survive_the_trip(self):
        payload = self.payload(story="First para.\n\nSecond para.")
        self.run_import(self.write(payload))
        story = SacredSitePage.objects.get(slug="test-mission").the_story
        self.assertEqual(story, "<p>First para.</p><p>Second para.</p>")

    def test_a_dry_run_saves_nothing(self):
        self.run_import(self.write(self.payload()), "--dry-run")
        self.assertFalse(SacredSitePage.objects.filter(slug="test-mission").exists())
        self.assertFalse(PilgrimageTrailPage.objects.filter(slug="test-trail").exists())

    def test_a_rerun_does_not_overwrite_edited_narrative(self):
        """The rule that makes re-running safe. Without it, one import undoes
        an afternoon of writing in the admin."""
        path = self.write(self.payload())
        self.run_import(path)

        site = SacredSitePage.objects.get(slug="test-mission")
        site.the_story = "<p>Rewritten by hand.</p>"
        site.save()

        self.run_import(path)
        self.assertEqual(
            SacredSitePage.objects.get(slug="test-mission").the_story,
            "<p>Rewritten by hand.</p>",
        )

    def test_overwrite_is_available_when_it_is_asked_for(self):
        path = self.write(self.payload())
        self.run_import(path)
        site = SacredSitePage.objects.get(slug="test-mission")
        site.the_story = "<p>Rewritten by hand.</p>"
        site.save()

        self.run_import(path, "--overwrite")
        self.assertIn(
            "Imported story.",
            SacredSitePage.objects.get(slug="test-mission").the_story,
        )

    def test_a_rerun_leaves_reordered_stops_alone(self):
        path = self.write(self.payload())
        self.run_import(path)
        trail = PilgrimageTrailPage.objects.get(slug="test-trail")
        stop_ids = [s.pk for s in trail.ordered_stops]

        self.run_import(path)
        trail = PilgrimageTrailPage.objects.get(slug="test-trail")
        self.assertEqual([s.pk for s in trail.ordered_stops], stop_ids)

    def test_replace_stops_rebuilds_the_route(self):
        path = self.write(self.payload())
        self.run_import(path)

        payload = self.payload()
        payload["trail"]["stops"] = [{"name": "Only stop", "latitude": 1, "longitude": 1}]
        self.run_import(self.write(payload), "--replace-stops")

        trail = PilgrimageTrailPage.objects.get(slug="test-trail")
        self.assertEqual([s.display_title for s in trail.stops_for_display], ["Only stop"])

    def test_draft_creates_unpublished_pages(self):
        self.run_import(self.write(self.payload()), "--draft")
        self.assertFalse(PilgrimageTrailPage.objects.get(slug="test-trail").live)
        self.assertFalse(SacredSitePage.objects.get(slug="test-mission").live)

    def test_a_missing_site_page_degrades_to_a_waypoint(self):
        """The Camino names Santiago by slug AND by coordinates on purpose."""
        payload = self.payload()
        payload["sites"] = []
        payload["trail"]["stops"][0] = {
            "site": "not-here",
            "name": "Santiago de Compostela",
            "latitude": 42.88052,
            "longitude": -8.54569,
        }
        self.run_import(self.write(payload))

        trail = PilgrimageTrailPage.objects.get(slug="test-trail")
        self.assertEqual(
            [s.display_title for s in trail.stops_for_display],
            ["Santiago de Compostela", "A waypoint"],
        )


class ShippedDataFileTests(TrailTestCase):
    """The three data files are content, and content can be typo'd.

    Imported for real against the page tree, so a bad category, a missing
    coordinate or a stop pointing at a slug that no file creates fails here
    rather than in production.
    """

    DATA = Path(__file__).resolve().parent / "data"

    def setUp(self):
        super().setUp()
        root = self.site_root()
        for slug, title in [
            ("shrines-and-basilicas", "Shrines & Basilicas"),
            ("marian-apparitions", "Marian Apparitions"),
            ("eucharistic-miracles", "Eucharistic Miracles"),
            ("saints-and-tombs", "Saints & Tombs"),
            ("holy-lands", "Holy Lands"),
            ("pilgrimage-routes", "Pilgrimage Routes"),
        ]:
            root.add_child(instance=StandardPage(title=title, slug=slug))

    def test_the_mission_trail_imports_with_all_twenty_one_missions(self):
        self.run_import(str(self.DATA / "california-mission-trail.json"))

        trail = PilgrimageTrailPage.objects.get(slug="california-mission-trail")
        self.assertEqual(len(trail.stops_for_display), 21)
        self.assertEqual(len(trail.mapped_stops), 21)
        self.assertEqual(len(trail.site_stops), 21)
        # South to north -- the order a pilgrim drives, not the order the
        # missions were founded. A line drawn in founding order zigzags the
        # length of the state.
        self.assertEqual(
            trail.stops_for_display[0].display_title, "Mission San Diego de Alcalá"
        )
        self.assertEqual(
            trail.stops_for_display[-1].display_title, "Mission San Francisco Solano"
        )
        latitudes = [float(stop.latitude) for stop in trail.stops_for_display]
        self.assertEqual(latitudes, sorted(latitudes))

        # Every mission page carries its own band back to the trail.
        first = SacredSitePage.objects.get(slug="mission-san-diego-de-alcala")
        self.assertEqual(first.trail_positions[0]["number"], 1)
        self.assertEqual(first.trail_positions[0]["total"], 21)

    def test_the_camino_imports_as_waypoints_and_draws(self):
        self.run_import(str(self.DATA / "camino-de-santiago.json"))

        trail = PilgrimageTrailPage.objects.get(slug="camino-de-santiago")
        self.assertEqual(len(trail.stops_for_display), len(trail.mapped_stops))
        self.assertTrue(trail.has_map)
        self.assertEqual(
            trail.stops_for_display[0].display_title, "Saint-Jean-Pied-de-Port"
        )
        self.assertEqual(
            trail.stops_for_display[-1].display_title, "Santiago de Compostela"
        )

    def test_the_three_new_sites_import_and_render(self):
        self.run_import(str(self.DATA / "new-sites-2026-09.json"))

        for slug in [
            "loretto-chapel-santa-fe",
            "scala-santa-holy-stairs-rome",
            "christ-cathedral-garden-grove",
        ]:
            site = SacredSitePage.objects.get(slug=slug)
            self.assertTrue(site.latitude and site.longitude, slug)
            self.assertTrue(site.summary_short, slug)
            self.assertTrue(site.has_plan_section, slug)
            self.assertEqual(self.client.get(site.url).status_code, 200, slug)

    def test_loretto_says_plainly_that_no_miracle_has_been_declared(self):
        """A page about a contested claim that reads as an endorsement is the
        one failure mode worth a test of its own."""
        self.run_import(str(self.DATA / "new-sites-2026-09.json"))
        site = SacredSitePage.objects.get(slug="loretto-chapel-santa-fe")
        self.assertEqual(site.canonical_status, "Not Applicable")
        self.assertIn("never investigated or declared", site.church_recognition)
        self.assertIn("no longer a Catholic church", site.church_recognition)


class HubCardTests(TrailTestCase):
    def test_pilgrimage_routes_lights_up_once_a_trail_is_published(self):
        """It was hardcoded unclickable. Now the first live trail does it."""
        hub = StandardPage(title="Explore", slug="explore", layout="explore_hub")
        self.site_root().add_child(instance=hub)
        routes = StandardPage(title="Pilgrimage Routes", slug="pilgrimage-routes")
        hub.add_child(instance=routes)

        hub = StandardPage.objects.get(pk=hub.pk)
        card = [c for c in hub._get_hub_cards() if c["title"] == "Pilgrimage Routes"][0]
        self.assertFalse(card["clickable"])

        routes.add_child(instance=PilgrimageTrailPage(title="A Trail", slug="a-trail"))

        hub = StandardPage.objects.get(pk=hub.pk)
        card = [c for c in hub._get_hub_cards() if c["title"] == "Pilgrimage Routes"][0]
        self.assertTrue(card["clickable"])

    def test_a_trail_gets_a_directory_card_in_its_own_line_color(self):
        routes = StandardPage(
            title="Pilgrimage Routes", slug="pilgrimage-routes", layout="category_directory"
        )
        self.site_root().add_child(instance=routes)
        routes.add_child(instance=PilgrimageTrailPage(
            title="The Camino", slug="camino", line_color="navy",
            trail_type="Walking route", summary_short="To Santiago.",
        ))

        cards = StandardPage.objects.get(pk=routes.pk)._get_directory_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["chip"], "Walking route")
        self.assertEqual(cards[0]["style"]["fill"], "#032553")
