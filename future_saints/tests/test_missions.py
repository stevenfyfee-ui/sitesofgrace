"""Phase 3: the California Missions hub, map accuracy, seed_mission_hub, the
projects guide and Build This Mission.

The 21 fixture missions use the Mission Trail pages' own coordinates and
founding text (as in the catalog); titles keep the catalog's forms, e.g.
"Mission Basilica San Juan Capistrano", to exercise the name matching. The
map is tested for accuracy, not looks: every pin inside the state outline,
the southern and northern extremes, north-to-south order, the Monterey and
SF Bay clusters against real distances, and pins that follow lat/lng.
"""
import json
import os
import re
import tempfile
from decimal import Decimal
from io import StringIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from catalog.models import PilgrimageTrailPage, SacredSitePage, TrailStop
from future_saints.geo import albers, point_in_polygon, to_viewbox
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.missions import (
    MissionProjectsGuidePage,
    MissionSchoolProject,
    ProjectFactCardRow,
    ProjectMaterial,
    ProjectSource,
    ProjectStep,
    california_outline,
    project_publish_problems,
)
from future_saints.models import FutureSaintsIndexPage, MissionHubEntry, MissionLearningPage

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase

FOUNDING_FILE = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content" / "missions-founding-order.json"

# founding #: (catalog title, latitude, longitude, catalog founding text)
MISSIONS = {
    1: ("Mission San Diego de Alcalá", 32.784267, -117.106283, "Founded July 16, 1769"),
    2: ("Mission San Carlos Borromeo de Carmelo (Carmel Mission)", 36.542778, -121.919167, "Founded June 3, 1770"),
    3: ("Mission San Antonio de Padua", 36.015000, -121.250000, "Founded July 14, 1771"),
    4: ("Mission San Gabriel Arcángel", 34.096668, -118.106667, "Founded September 8, 1771"),
    5: ("Mission San Luis Obispo de Tolosa", 35.280560, -120.664440, "Founded September 1, 1772"),
    6: ("Mission San Francisco de Asís (Mission Dolores)", 37.764389, -122.427025, "Founded October 9, 1776"),
    7: ("Mission Basilica San Juan Capistrano", 33.501000, -117.662000, "Founded 1776"),
    8: ("Mission Santa Clara de Asís", 37.349300, -121.941498, "Founded January 12, 1777"),
    9: ("Mission San Buenaventura", 34.280950, -119.297817, "Founded March 31, 1782"),
    10: ("Mission Santa Bárbara", 34.438367, -119.713133, "Founded December 4, 1786"),
    11: ("Mission La Purísima Concepción", 34.670683, -120.420883, "Founded December 8, 1787"),
    12: ("Mission Santa Cruz", 36.978417, -122.029767, "Founded August 28, 1791"),
    13: ("Mission Nuestra Señora de la Soledad", 36.404619, -121.355807, "Founded October 9, 1791"),
    14: ("Mission San José", 37.532780, -121.919440, "Founded June 11, 1797"),
    15: ("Mission San Juan Bautista", 36.845717, -121.535533, "Founded June 24, 1797"),
    16: ("Mission San Miguel Arcángel", 35.744720, -120.698060, "Founded July 25, 1797"),
    17: ("Mission San Fernando Rey de España", 34.273100, -118.461200, "Founded September 8, 1797"),
    18: ("Mission San Luis Rey de Francia", 33.232500, -117.320280, "Founded June 13, 1798"),
    19: ("Mission Santa Inés", 34.594440, -120.136940, "Founded September 17, 1804"),
    20: ("Mission San Rafael Arcángel", 37.974333, -122.527917, "Founded December 14, 1817"),
    21: ("Mission San Francisco Solano", 38.293667, -122.455917, "Founded July 4, 1823"),
}
MONTEREY_CLUSTER = (2, 13, 15)
BAY_CLUSTER = (6, 8, 12, 14, 20, 21)
BANNED_WORDS = ("buy", "shop", "store", "price", "amazon", "amzn", "affiliate")


def km(a, b):
    """Great-circle distance in km between two (lat, lng)."""
    (la1, lo1), (la2, lo2) = [(radians(x), radians(y)) for x, y in (a, b)]
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def slug_of(n):
    return f"fixture-mission-{n}"


class MissionsTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        # Fixture pages get database ids that can be anything, including production's
        # duplicate ids; the exclusion list is tested on its own (SeedTests).
        patcher = mock.patch("future_saints.management.commands.seed_mission_hub.EXCLUDED_DUPLICATES", set())
        patcher.start()
        self.addCleanup(patcher.stop)
        root = self.home.get_parent()
        self.sites = {}
        for n, (title, lat, lng, text) in MISSIONS.items():
            site = SacredSitePage(title=title, slug=slug_of(n), category="Shrine & Basilica",
                                  latitude=Decimal(str(lat)), longitude=Decimal(str(lng)), date_display=text)
            root.add_child(instance=site)
            self.sites[n] = site
        trail = PilgrimageTrailPage(title="California Mission Trail", slug=MISSION_TRAIL_SLUG)
        by_south = sorted(self.sites.values(), key=lambda s: s.latitude)
        trail.stops = [TrailStop(site=s, sort_order=i) for i, s in enumerate(by_south)]
        root.add_child(instance=trail)
        self.trail = trail
        self.hub = FutureSaintsIndexPage.objects.get(content_kind="california_mission")

    def seed(self, *flags, path=None):
        out = StringIO()
        call_command("seed_mission_hub", *([path] if path else []), *flags, stdout=out)
        return out.getvalue()

    def seed_and_publish(self):
        self.seed()
        self.hub.refresh_from_db()          # the seed saved a new latest revision
        self.hub.get_latest_revision().publish()
        self.hub.refresh_from_db()

    def hub_html(self, user=None, **params):
        with FS_ON:
            return self.html(self.hub.url, user, **params)

    def story(self, n, **fields):
        page = MissionLearningPage(title=f"Story {n}", slug=f"story-{n}", canonical=self.sites[n],
                                   student_title=MISSIONS[n][0], subtitle=f"Subtitle {n} (sample)",
                                   intro=f"<p>Intro for mission {n} (sample).</p>", **fields)
        self.hub.add_child(instance=page)
        page.save_revision().publish()
        return MissionLearningPage.objects.get(pk=page.pk)

    def project(self, page, status="published", **fields):
        project = MissionSchoolProject(
            page=page, project_title=f"Build This Mission: {page.student_title} (sample)", status=status,
            model_reference_image=get_image_model().objects.create(title="Ref", file=get_test_image_file()),
            model_reference_image_alt="The mission church today (sample)",
            adult_supervision_notes="A grown-up does all cutting (sample).", **fields)
        project.materials = [ProjectMaterial(item="Cardboard (sample)", quantity="1")]
        project.steps = [ProjectStep(title=f"Step {i} (sample)", instructions="Do this (sample).") for i in range(3)]
        project.sources = [ProjectSource(title="A source (sample)", url="https://example.com/source")]
        project.save()
        page.refresh_from_db()
        return project


class ProjectionTests(MissionsTestCase):
    def test_albers_matches_epsg_3310(self):
        # Reference values from PROJ (pyproj, EPSG:4269 -> EPSG:3310), checked when geo.py was written.
        for (lat, lng), (x, y) in {
            (32.7843, -117.1061): (271423.202, -576773.025),
            (38.2939, -122.4581): (-214699.313, 33635.667),
            (42.0, -120.0): (0.0, 442428.987),
        }.items():
            px, py = albers(lat, lng)
            self.assertAlmostEqual(px, x, places=2)
            self.assertAlmostEqual(py, y, places=2)

    def test_outline_is_public_domain_and_documented(self):
        outline = california_outline()
        self.assertIn("Public domain", outline["source"]["licence"])
        self.assertIn("census.gov", outline["source"]["url"])
        self.assertTrue(outline["path"].startswith("M"))
        doc = (Path(settings.BASE_DIR) / "docs" / "future-saints" / "map-calibration.md").read_text(encoding="utf-8")
        for needed in ("EPSG:3310", "viewBox", "San Diego", "Sonoma", "census.gov"):
            self.assertIn(needed, doc)

    def test_border_control_points_match_the_outline(self):
        mainland = california_outline()["rings"][0]
        south = max(mainland, key=lambda p: p[1])
        northwest = min(mainland, key=lambda p: p[1])
        for (lat, lng), vertex in (((32.5343, -117.1235), south), ((41.9983, -124.2125), northwest)):
            x, y = to_viewbox(lat, lng)
            self.assertLess(((x - vertex[0]) ** 2 + (y - vertex[1]) ** 2) ** .5, 1.0, (lat, lng))

    def pins(self):
        return {n: to_viewbox(lat, lng) for n, (_, lat, lng, _) in MISSIONS.items()}

    def test_all_21_pins_fall_inside_the_state(self):
        mainland = california_outline()["rings"][0]
        for n, (x, y) in self.pins().items():
            self.assertTrue(point_in_polygon(x, y, mainland), f"#{n} {MISSIONS[n][0]} at ({x:.1f}, {y:.1f})")

    def test_extremes_san_diego_south_sonoma_north(self):
        pins = self.pins()
        self.assertEqual(max(pins, key=lambda n: pins[n][1]), 1, "southernmost (largest y) is San Diego")
        self.assertEqual(min(pins, key=lambda n: pins[n][1]), 21, "northernmost (smallest y) is Sonoma")

    def test_north_to_south_order_matches_latitude(self):
        """Every pair more than 0.05° (about 5.5 km) apart in latitude is in the same order by
        projected y. Closer pairs may swap: on a conic projection the parallels are arcs, so of
        two points at almost the same latitude the one further from 120°W plots a little higher
        (San Fernando #17 vs San Buenaventura #9, 0.008° apart)."""
        pins = self.pins()
        for a in MISSIONS:
            for b in MISSIONS:
                if MISSIONS[a][1] - MISSIONS[b][1] > .05:          # a is clearly north of b
                    self.assertLess(pins[a][1], pins[b][1], f"#{a} should be above #{b}")

    def test_clusters_sit_at_their_real_distances(self):
        pins = self.pins()
        for cluster in (MONTEREY_CLUSTER, BAY_CLUSTER):
            for a in cluster:
                for b in cluster:
                    if a >= b:
                        continue
                    real = km(MISSIONS[a][1:3], MISSIONS[b][1:3])
                    mapped = 1.1 * ((pins[a][0] - pins[b][0]) ** 2 + (pins[a][1] - pins[b][1]) ** 2) ** .5
                    self.assertLess(abs(mapped - real), .03 * real + .5, f"#{a}–#{b}: map {mapped:.1f} km vs {real:.1f} km")
            cx = sum(pins[n][0] for n in cluster) / len(cluster)
            cy = sum(pins[n][1] for n in cluster) / len(cluster)
            for n in cluster:
                self.assertLess(((pins[n][0] - cx) ** 2 + (pins[n][1] - cy) ** 2) ** .5, 80, f"#{n} near its cluster")

    def test_decorations_stay_in_the_ocean(self):
        rings = california_outline()["rings"]
        decor = {"compass": (110 - 52, 990 - 60, 110 + 52, 990 + 52), "scroll": (60 - 8, 765 + 8, 60 + 248, 765 + 82)}
        for name, (x1, y1, x2, y2) in decor.items():
            for x in range(int(x1), int(x2) + 1, 4):
                for y in range(int(y1), int(y2) + 1, 4):
                    self.assertFalse(any(point_in_polygon(x, y, r) for r in rings), f"{name} touches land at ({x}, {y})")

    def test_a_pin_moves_when_its_canonical_lat_lng_changes(self):
        self.seed_and_publish()
        before = re.search(r'value="fixture-mission-12"[^>]*style="--x: ([\d.]+)%; --y: ([\d.]+)%', self.hub_html())
        site = self.sites[12]
        site.latitude, site.longitude = Decimal("36.9"), Decimal("-121.9")
        site.save_revision().publish()
        after = re.search(r'value="fixture-mission-12"[^>]*style="--x: ([\d.]+)%; --y: ([\d.]+)%', self.hub_html())
        self.assertNotEqual(before.groups(), after.groups())
        x, y = to_viewbox(36.9, -121.9)
        self.assertEqual(after.groups(), (f"{100 * x / 1000:.3f}", f"{100 * y / 1100:.3f}"))


class SeedTests(MissionsTestCase):
    def test_dry_run_table_and_flags(self):
        out = self.seed("--dry-run")
        rows = [line for line in out.splitlines() if re.match(r"^\s?\d{1,2} \| ", line)]
        self.assertEqual(len(rows), 21)
        self.assertEqual(sum(row.endswith("| yes") for row in rows), 21)
        self.assertIn(f"#{self.sites[7].pk} Mission Basilica San Juan Capistrano", out)
        self.assertIn("32.784267, -117.106283", out)
        self.assertIn("flag: #6", out)
        self.assertIn("dedication", out)
        self.assertIn("flag: #7", out)
        self.assertIn("year only", out)
        self.assertIn("Would save a draft revision", out)
        self.assertEqual(self.hub.mission_hub_entries.count(), 0, "dry run writes nothing")

    def test_seed_writes_a_draft_revision_and_is_idempotent(self):
        out = self.seed()
        self.assertIn("Saved a draft revision", out)
        self.hub.refresh_from_db()
        self.assertTrue(self.hub.has_unpublished_changes, "a draft, never published by the command")
        self.assertEqual(self.hub.mission_hub_entries.count(), 0, "the live page is untouched")
        latest = self.hub.get_latest_revision_as_object()
        entries = sorted(latest.mission_hub_entries.all(), key=lambda e: e.founding_number)
        self.assertEqual([e.founding_number for e in entries], list(range(1, 22)))
        self.assertEqual(entries[0].canonical_id, self.sites[1].pk)
        self.assertEqual(entries[0].founded_display, "July 16, 1769")
        self.assertEqual(entries[6].founded_display, "1776")
        revisions = self.hub.revisions.count()
        self.assertIn("Unchanged", self.seed())
        self.assertEqual(self.hub.revisions.count(), revisions)

    def test_never_uses_the_older_duplicate_pages(self):
        # Production's duplicates are #1144 and #1126. Here the duplicate gets whatever id the
        # database gives it (a forced pk would collide with later tests' pages), and the
        # exclusion list is pointed at it.
        duplicate = SacredSitePage(title="Mission Basilica San Diego de Alcala", slug="mission-basilica-san-diego",
                                   category="Shrine & Basilica", latitude=Decimal("32.7"), longitude=Decimal("-117.1"))
        self.home.get_parent().add_child(instance=duplicate)
        TrailStop.objects.create(trail=self.trail, site=duplicate, sort_order=99)   # saved, not just in the cluster
        self.assertIn("2 match(es)", self.failing_seed(), "without the exclusion it is a double match")
        with mock.patch("future_saints.management.commands.seed_mission_hub.EXCLUDED_DUPLICATES", {duplicate.pk}):
            out = self.seed("--dry-run")
        self.assertIn(f"#{self.sites[1].pk} Mission San Diego de Alcalá", out)
        self.assertIn("21 live Mission Trail stop page(s)", out, "22 stops on the trail, the duplicate excluded")
        self.assertNotIn(f"#{duplicate.pk} Mission Basilica", out.split("excluded duplicates")[1])

    def test_production_duplicates_are_1144_and_1126(self):
        from future_saints.management.commands import seed_mission_hub

        self.assertEqual(seed_mission_hub.EXCLUDED_DUPLICATES.__class__, set)
        with open(seed_mission_hub.__file__, encoding="utf-8") as fh:
            self.assertIn("EXCLUDED_DUPLICATES = {1144, 1126}", fh.read())

    def failing_seed(self):
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("seed_mission_hub", "--dry-run", stdout=out)
        return out.getvalue()

    def test_no_match_or_double_match_stops_and_writes_nothing(self):
        self.sites[14].unpublish()
        with self.assertRaises(CommandError):
            out = StringIO()
            call_command("seed_mission_hub", stdout=out)
        self.assertIn("#14 'Mission San José': 0 match(es)", out.getvalue())
        self.sites[14].save_revision().publish()
        twin = SacredSitePage(title="Mission San José (second)", slug="twin-jose", category="Shrine & Basilica",
                              latitude=Decimal("37.5"), longitude=Decimal("-121.9"))
        self.home.get_parent().add_child(instance=twin)
        TrailStop.objects.create(trail=self.trail, site=twin, sort_order=50)
        with self.assertRaises(CommandError):
            out = StringIO()
            call_command("seed_mission_hub", stdout=out)
        self.assertIn("#14 'Mission San José': 2 match(es)", out.getvalue())
        self.assertFalse(self.hub.revisions.exists() and self.hub.get_latest_revision_as_object().mission_hub_entries.exists())

    def test_year_mismatch_is_reported_not_fixed(self):
        data = json.loads(FOUNDING_FILE.read_text(encoding="utf-8"))
        data["missions"][2]["founded_year"] = 1772
        path = os.path.join(tempfile.mkdtemp(), "order.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        out = self.seed("--dry-run", path=path)
        self.assertIn("NO (file 1772, page 1771)", out)
        self.assertIn("year mismatch", out)


class HubTests(MissionsTestCase):
    def setUp(self):
        super().setUp()
        self.seed_and_publish()

    def pins(self, html):
        return re.findall(r'<button type="submit" name="mission" value="([^"]+)" class="fs-pin"[^>]*aria-label="([^"]+)"[^>]*aria-pressed="(true|false)"', html, re.S)

    def test_switch_gating_and_noindex(self):
        with FS_OFF:
            self.assertEqual(self.get(self.hub.url, self.staff).status_code, 404)
        with FS_STAFF:
            self.assertEqual(self.get(self.hub.url).status_code, 404)
            response = self.get(self.hub.url, self.staff)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
        with FS_ON:
            self.assertEqual(self.get(self.hub.url).status_code, 200)

    def test_21_pins_in_founding_order_with_labels(self):
        pins = self.pins(self.hub_html())
        self.assertEqual(len(pins), 21)
        self.assertEqual([p[0] for p in pins], [slug_of(n) for n in range(1, 22)], "tab order = founding order")
        self.assertEqual(pins[0][1], "Mission San Diego de Alcalá, Founding number 1, founded 1769")
        self.assertEqual([p[2] for p in pins].count("true"), 1)
        self.assertEqual(pins[0][2], "true", "default selection is #1")

    def test_no_js_selection_by_query(self):
        html = self.hub_html(mission=slug_of(12))
        pins = self.pins(html)
        self.assertEqual([p[0] for p in pins if p[2] == "true"], [slug_of(12)])
        self.assertIn('data-fs-panel-name>Mission Santa Cruz<', html)
        self.assertIn('<form class="fs-map-pins" method="get" action="#mission-panel"', html)
        self.assertIn('name="mission"', html)
        unknown = self.hub_html(mission="nope")
        self.assertIn('data-fs-panel-name>Mission San Diego de Alcalá<', unknown)

    def test_three_lists_of_21(self):
        html = self.hub_html()
        for list_id in ("list-order", "list-ns", "list-az"):
            block = html.split(f'id="{list_id}"')[1].split("</div>")[0]
            self.assertEqual(block.count("<li>"), 21, list_id)
        north_south = re.findall(r'\?mission=([\w-]+)#', html.split('id="list-ns"')[1].split("</div>")[0])
        self.assertEqual(north_south[0], slug_of(21))
        self.assertEqual(north_south[-1], slug_of(1))
        az = html.split('id="list-az"')[1].split("</div>")[0]
        self.assertLess(az.index("La Purísima"), az.index("Nuestra Señora"))
        timeline = html.split('id="founding-order"')[1].split("</section>")[0]
        self.assertEqual(timeline.count("<li>"), 21)
        self.assertIn("Founding #7</span> <a href=\"?mission=fixture-mission-7#mission-panel\">Mission Basilica San Juan Capistrano</a> · 1776", timeline)

    def test_close_pin_chooser_markup(self):
        html = self.hub_html()
        self.assertIn('data-fs-pin-radius="24"', html)
        self.assertIn('data-fs-chooser', html)
        self.assertIn('role="dialog"', html)

    def test_panel_states(self):
        html = self.hub_html(mission=slug_of(5))
        panel = html.split('id="mission-panel"')[1].split("</aside>")[0]
        self.assertIn("This mission's story is coming soon.", panel)
        self.assertIn("data-fs-panel-story hidden", panel)
        self.assertIn("Founded: <span data-fs-panel-founded>September 1, 1772</span>", panel)

        page = self.story(5)
        panel = self.hub_html(mission=slug_of(5)).split('id="mission-panel"')[1].split("</aside>")[0]
        self.assertIn("Subtitle 5 (sample)", panel)
        self.assertIn("Intro for mission 5 (sample).", panel)
        self.assertIn(f'href="{page.url}" data-fs-panel-read', panel)
        self.assertIn("data-fs-panel-build hidden", panel, "no project yet")

        self.project(page)
        panel = self.hub_html(mission=slug_of(5)).split('id="mission-panel"')[1].split("</aside>")[0]
        self.assertIn(f'href="{page.url}#build" data-fs-panel-build>', panel)

        page.school_projects.update(status="review_ready")
        panel = self.hub_html(mission=slug_of(5)).split('id="mission-panel"')[1].split("</aside>")[0]
        self.assertIn("data-fs-panel-build hidden", panel, "only a published project links")

    def test_four_cards_and_their_sections(self):
        html = self.hub_html()
        cards = re.findall(r'<a class="fs-lcard" href="#([a-z-]+)">.*?<span class="fs-lcard-title">(.*?)</span>', html, re.S)
        self.assertEqual(cards, [("mission-stories", "Mission Stories"), ("founding-order", "Timeline"),
                                 ("native-peoples", "Native Peoples"), ("quiz", "Test Your Knowledge")])
        for anchor, _ in cards:
            self.assertIn(f'id="{anchor}"', html)
        self.assertIn("Mission stories are coming soon.", html)
        self.story(1)
        self.assertNotIn("Mission stories are coming soon.", self.hub_html())

    def hub_form_data(self):
        form_class = FutureSaintsIndexPage.get_edit_handler().get_form_class()
        blank = form_class(instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent())
        data = {n: (v.pk if hasattr(v, "pk") else v) for n, f in blank.fields.items()
                if (v := blank.initial.get(n, f.initial)) not in (None, "")}
        for prefix in blank.formsets:
            data.update({f"{prefix}-TOTAL_FORMS": 0, f"{prefix}-INITIAL_FORMS": 0,
                         f"{prefix}-MIN_NUM_FORMS": 0, f"{prefix}-MAX_NUM_FORMS": 1000})
        return form_class, data

    def test_hub_entries_form_rejects_a_repeated_number_or_mission(self):
        form_class, data = self.hub_form_data()
        data["mission_hub_entries-TOTAL_FORMS"] = 2
        for i, (n, site) in enumerate([(1, 1), (1, 2)]):
            data.update({f"mission_hub_entries-{i}-canonical": self.sites[site].pk, f"mission_hub_entries-{i}-founding_number": n,
                         f"mission_hub_entries-{i}-founded_year": 1769, f"mission_hub_entries-{i}-founded_display": "x",
                         f"mission_hub_entries-{i}-ORDER": i})
        form = form_class(data, instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent())
        self.assertFalse(form.is_valid())
        data["mission_hub_entries-1-founding_number"] = 2
        data["mission_hub_entries-1-canonical"] = self.sites[1].pk
        form = form_class(data, instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent())
        self.assertFalse(form.is_valid())
        data["mission_hub_entries-1-canonical"] = self.sites[2].pk
        form = form_class(data, instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent())
        self.assertTrue(form.is_valid(), form.errors)

    def test_hub_quiz_rules_in_the_admin_form(self):
        form_class, data = self.hub_form_data()
        data["hub_quiz_questions-TOTAL_FORMS"] = 1
        data["hub_quiz_questions-0-prompt"] = "How many? (sample)"
        cp = "hub_quiz_questions-0-choices"
        data.update({f"{cp}-TOTAL_FORMS": 2, f"{cp}-INITIAL_FORMS": 0, f"{cp}-MIN_NUM_FORMS": 0, f"{cp}-MAX_NUM_FORMS": 4,
                     f"{cp}-0-text": "A", f"{cp}-1-text": "B", f"{cp}-1-is_correct": "on"})
        self.assertFalse(form_class(data, instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent()).is_valid())
        data.update({f"{cp}-TOTAL_FORMS": 3, f"{cp}-2-text": "C"})
        form = form_class(data, instance=self.hub, for_user=self.staff, parent_page=self.hub.get_parent())
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_indexes_keep_their_own_template(self):
        with FS_ON:
            html = self.html(self.saints.url)
        self.assertNotIn("data-fs-map", html)


class ProjectTests(MissionsTestCase):
    def setUp(self):
        super().setUp()
        self.seed_and_publish()
        self.page = self.story(1)

    def mission_html(self, page=None, **params):
        with FS_ON:
            return self.html((page or self.page).url, **params)

    def test_publish_problems_never_ask_for_a_credit(self):
        self.assertEqual(project_publish_problems(image=object(), alt="Alt", steps=3, materials=1, sources=1,
                                                  adult_notes="Notes"), [])
        problems = project_publish_problems(image=None, alt="", steps=2, materials=0, sources=0, adult_notes="")
        self.assertEqual(len(problems), 6)
        self.assertFalse(any("credit" in p.lower() for p in problems))

    def admin_form(self, status, image=True, steps=3):
        form_class = MissionLearningPage.get_edit_handler().get_form_class()
        blank = form_class(instance=self.page, for_user=self.staff, parent_page=self.hub)
        data = {}
        for name, field in blank.fields.items():
            value = blank.initial.get(name, field.initial)
            if value in (None, "") or name in ("intro", "story"):
                continue
            data[name] = value.pk if hasattr(value, "pk") else value
        for prefix in blank.formsets:
            data.update({f"{prefix}-TOTAL_FORMS": 0, f"{prefix}-INITIAL_FORMS": 0,
                         f"{prefix}-MIN_NUM_FORMS": 0, f"{prefix}-MAX_NUM_FORMS": 1000})
        p = "school_projects-0"
        data.update({"school_projects-TOTAL_FORMS": 1, f"{p}-project_title": "Build This Mission (sample)",
                     f"{p}-status": status, f"{p}-model_reference_image_alt": "The church today (sample)",
                     f"{p}-adult_supervision_notes": "A grown-up cuts (sample).", f"{p}-ORDER": 0})
        if image:
            data[f"{p}-model_reference_image"] = get_image_model().objects.create(title="Ref", file=get_test_image_file()).pk
        rows = {"features": [], "materials": [{"item": "Cardboard (sample)"}],
                "steps": [{"title": f"Step {i} (sample)", "instructions": "Do it (sample)."} for i in range(steps)],
                "fact_card_rows": [], "sources": [{"title": "Source (sample)", "url": "https://example.com/"}]}
        for name, items in rows.items():
            data.update({f"{p}-{name}-TOTAL_FORMS": len(items), f"{p}-{name}-INITIAL_FORMS": 0,
                         f"{p}-{name}-MIN_NUM_FORMS": 0, f"{p}-{name}-MAX_NUM_FORMS": 1000})
            for i, item in enumerate(items):
                data.update({f"{p}-{name}-{i}-{k}": v for k, v in item.items()})
                data[f"{p}-{name}-{i}-ORDER"] = i
        return form_class(data, instance=self.page, for_user=self.staff, parent_page=self.hub)

    def test_publish_validation_in_the_admin(self):
        form = self.admin_form("published")
        self.assertTrue(form.is_valid(), form.errors)                       # no credit needed
        self.assertFalse(self.admin_form("published", image=False).is_valid())
        self.assertFalse(self.admin_form("published", steps=2).is_valid())
        draft = self.admin_form("draft", image=False, steps=0)
        self.assertTrue(draft.is_valid(), draft.errors)                     # drafts can be incomplete

    def test_project_shows_only_when_published_and_card_follows(self):
        project = self.project(self.page, status="review_ready")
        html = self.mission_html()
        self.assertNotIn(project.project_title, html)
        self.assertIn('href="#quiz"', html.split('class="fs-lcards"')[1].split("</ul>")[0])
        project.status = "published"
        project.save()
        html = self.mission_html()
        self.assertIn('<h2 id="build-h" class="fs-block-title">Build This Mission: Mission San Diego de Alcalá (sample)</h2>', html)
        cards = html.split('class="fs-lcards"')[1].split("</ul>")[0]
        self.assertIn('href="#build"', cards)
        self.assertNotIn('href="#quiz"', cards)
        self.assertIn('alt="The mission church today (sample)"', html)

    def test_credit_never_renders_on_the_project(self):
        self.project(self.page, model_reference_image_credit="PROJECT CREDIT NOTE (sample)")
        html = self.mission_html()
        self.assertNotIn("PROJECT CREDIT NOTE", html)
        for sheet in ("materials", "steps", "factcard"):
            self.assertNotIn("PROJECT CREDIT NOTE", self.mission_html(print=sheet))

    def test_three_print_views(self):
        project = self.project(self.page)
        ProjectFactCardRow.objects.create(project=project, label="Founding #", value="1", sort_order=0)
        for sheet, title in (("materials", "Materials Checklist"), ("steps", "Step-by-Step Instructions"), ("factcard", "Fact Card")):
            html = self.mission_html(print=sheet)
            self.assertIn(f"<title>{title} · Mission San Diego de Alcalá</title>", html, sheet)
            self.assertIn("future-saints-print-sheets.css", html)
            self.assertNotIn("data-fs-map", html)
        self.assertIn("Cardboard (sample)", self.mission_html(print="materials"))
        self.assertIn("Step 2 (sample)", self.mission_html(print="steps"))
        self.assertIn("<dt>Founding #</dt><dd>1</dd>", self.mission_html(print="factcard"))
        self.assertIn('class="fs-lcards"', self.mission_html(print="nonsense"), "unknown sheet: the normal page")

    def test_no_print_view_until_published(self):
        self.project(self.page, status="draft")
        self.assertIn('class="fs-lcards"', self.mission_html(print="materials"))

    def test_guide_grid_coming_soon_and_project_link(self):
        guide = MissionProjectsGuidePage(title="How to Build a California Mission Model (sample)", slug="projects")
        self.hub.add_child(instance=guide)
        guide.save_revision().publish()
        with FS_ON:
            html = self.html(guide.url)
        grid = html.split('class="fs-project-grid"')[1].split("</ol>")[0]
        self.assertEqual(grid.count("<li>"), 21)
        self.assertEqual(grid.count("Guide coming soon"), 21)
        self.assertNotIn("<a ", grid)
        self.project(self.page)
        with FS_ON:
            grid = self.html(guide.url).split('class="fs-project-grid"')[1].split("</ol>")[0]
        self.assertEqual(grid.count("Guide coming soon"), 20)
        self.assertIn(f'<a class="fs-project-tile" href="{self.page.url}#build">', grid)
        with FS_ON:
            self.assertEqual(self.get(guide.url + "?print=checklist").status_code, 200)

    def test_guide_lives_only_under_the_missions_index(self):
        self.assertTrue(MissionProjectsGuidePage.can_create_at(self.hub))
        self.assertFalse(MissionProjectsGuidePage.can_create_at(self.saints))

    def test_no_banned_words_anywhere(self):
        guide = MissionProjectsGuidePage(title="How to Build a California Mission Model (sample)", slug="projects")
        self.hub.add_child(instance=guide)
        guide.save_revision().publish()
        self.project(self.page)
        with FS_ON:
            pages = [self.html(self.hub.url), self.html(guide.url), self.html(guide.url + "?print=checklist")]
        pages += [self.mission_html(), self.mission_html(print="materials"), self.mission_html(print="steps"),
                  self.mission_html(print="factcard")]
        for html in pages:
            text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S).lower()
            for word in BANNED_WORDS:
                self.assertIsNone(re.search(rf"\b{word}\b", text), word)


class HubEntryValidationTests(MissionsTestCase):
    def test_hub_entry_numbers_are_1_to_21_and_unique(self):
        from django.core.exceptions import ValidationError

        entry = MissionHubEntry(page=self.hub, canonical=self.sites[1], founding_number=22, founded_year=1769,
                                founded_display="July 16, 1769")
        with self.assertRaises(ValidationError):
            entry.full_clean(exclude=["page"])
