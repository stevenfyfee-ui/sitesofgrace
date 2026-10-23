"""Phase 3 of Pilgrimage Platform v2: "Where to Stay & Map".

Protects: coordinate and route validation; the section threshold (one
lodging or two points); routes drawn only from valid GeoJSON; the layer
toggles in the markup; the importer's dry run, idempotency, draft skip and
conflict rule; the outbound counter storing nothing about the visitor; the
three pre-v2 maps left exactly as they were; and the switch hiding it all.
"""
import json
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template.loader import get_template
from django.test import override_settings

from catalog.models import LodgingClickDaily, SacredSitePage, SiteLodging, SiteMapPoint, parse_route_geojson
from catalog.tests_v2_site import V2SiteTestCase

V2_ON = override_settings(SOG_V2_ENABLED="on")
ROUTE = json.dumps({"type": "LineString", "coordinates": [[-0.0512, 43.0962], [-0.0531, 43.0957]]})


class StayMapTestCase(V2SiteTestCase):
    def site(self, slug="stay", **kwargs):
        kwargs.setdefault("latitude", Decimal("43.0967"))
        kwargs.setdefault("longitude", Decimal("-0.0558"))
        return self.make_site(slug=slug, **kwargs)

    def point(self, page, name="Gate (sample)", kind="main-entrance", lat="43.0957", lng="-0.0531"):
        return SiteMapPoint.objects.create(page=page, kind=kind, name=name, latitude=Decimal(lat),
                                           longitude=Decimal(lng))

    def lodging(self, page, name="Hotel (sample)", **kwargs):
        kwargs.setdefault("kind", "hotel")
        kwargs.setdefault("latitude", Decimal("43.0962"))
        kwargs.setdefault("longitude", Decimal("-0.0512"))
        return SiteLodging.objects.create(page=page, name=name, **kwargs)

    def section(self, html):
        return html.split('id="stay-map"')[1].split("</section>")[0]


class ValidationTests(StayMapTestCase):
    def test_route_must_be_a_linestring(self):
        self.assertEqual(parse_route_geojson(ROUTE), [[43.0962, -0.0512], [43.0957, -0.0531]])
        feature = {"type": "Feature", "geometry": json.loads(ROUTE)}
        self.assertEqual(len(parse_route_geojson(feature)), 2)
        for bad in ("not json", '{"type": "Point", "coordinates": [0, 0]}',
                    '{"type": "LineString", "coordinates": [[0, 0]]}',
                    '{"type": "LineString", "coordinates": [[0, 0], [200, 0]]}',
                    '{"type": "LineString", "coordinates": [["a", 0], [1, 1]]}'):
            with self.assertRaises(ValidationError, msg=bad):
                parse_route_geojson(bad)

    def test_model_validation(self):
        page = self.site()
        gate = self.point(page)
        chapel = self.point(page, name="Chapel", kind="sacred-place")
        lodging = SiteLodging(page=page, name="H", kind="hotel", latitude=Decimal("43.1"),
                              longitude=Decimal("-0.05"), route_geojson='{"type": "Point"}')
        with self.assertRaises(ValidationError) as ctx:
            lodging.full_clean()
        self.assertIn("route_geojson", ctx.exception.message_dict)
        lodging.route_geojson, lodging.nearest_point = ROUTE, chapel
        with self.assertRaises(ValidationError) as ctx:
            lodging.full_clean()
        self.assertIn("nearest_point", ctx.exception.message_dict)
        lodging.nearest_point = gate
        lodging.full_clean()
        bad = SiteMapPoint(page=page, kind="other", name="X", latitude=Decimal("95"), longitude=Decimal("0"))
        with self.assertRaises(ValidationError) as ctx:
            bad.full_clean()
        self.assertIn("latitude", ctx.exception.message_dict)


@V2_ON
class RenderTests(StayMapTestCase):
    def test_section_threshold(self):
        one_point = self.site("one-point")
        self.point(one_point)
        self.assertNotIn('id="stay-map"', self.html(one_point))
        two_points = self.site("two-points")
        self.point(two_points)
        self.point(two_points, name="Station", kind="train-station")
        html = self.html(two_points)
        self.assertIn('id="stay-map"', html)
        self.assertIn('data-section-link="stay-map"', html)
        one_lodging = self.site("one-lodging")
        self.lodging(one_lodging)
        self.assertIn('id="stay-map"', self.html(one_lodging))
        self.assertIn('href="#stay-map"', self.html(one_lodging), "Plan your own visit jumps to the map")

    def test_route_only_from_geojson(self):
        page = self.site("routes")
        gate = self.point(page)
        self.lodging(page, name="With route", nearest_point=gate, route_geojson=ROUTE, walk_minutes=4,
                     walk_miles=Decimal("0.2"), slope="level")
        self.lodging(page, name="Without route", nearest_point=gate)
        payload = SacredSitePage.objects.get(pk=page.pk).stay_map_payload()
        routes = {h["name"]: h["route"] for h in payload["lodgings"]}
        self.assertEqual(routes["With route"], [[43.0962, -0.0512], [43.0957, -0.0531]])
        self.assertIsNone(routes["Without route"])
        self.assertIn('"With route to Gate (sample): about 4 minutes on foot, 0.2 mi. Level."',
                      json.dumps([h["summary"] for h in payload["lodgings"]]))
        self.assertIn("Walking route not yet verified.", open(
            os.path.join(os.path.dirname(__file__), "static", "catalog", "js", "site-map.js"), encoding="utf-8").read())

    def test_layer_toggles_and_list_render_server_side(self):
        page = self.site("toggles")
        self.point(page)
        self.point(page, name="Chapel", kind="sacred-place")
        self.point(page, name="Station", kind="train-station")
        self.lodging(page, walk_minutes=7, walk_miles=Decimal("0.3"), slope="steep", step_free="no",
                     note="Hard climb back.", booking_url="https://example.com/b", is_affiliate_link=True)
        section = self.section(self.html(page))
        for layer, pressed in (("shrine", "true"), ("lodging", "true"), ("sacred", "true"), ("transit", "false")):
            self.assertIn(f'data-layer="{layer}" aria-pressed="{pressed}"', section)
        self.assertIn('id="siteStayMap"', section)
        self.assertIn("hidden></div>", section, "the map only appears once JS draws it")
        self.assertIn("7 min walk · 0.3 mi", section)
        self.assertIn('v2-lodge-pill v2-lodge-pill--warn">Steep', section)
        self.assertIn("Hard climb back.", section)
        lodging = SiteLodging.objects.get(page=page)
        self.assertIn(f'/go/lodging/{lodging.pk}/?from={page.pk}" target="_blank" rel="sponsored nofollow noopener"',
                      section)
        self.assertIn("Some booking links may earn us a commission", section)
        self.assertIn("js/sog-maps.js", section)
        self.assertNotIn("per night", section.lower())

    def test_empty_layers_get_no_toggle(self):
        page = self.site("no-transit")
        self.lodging(page)
        section = self.section(self.html(page))
        self.assertNotIn('data-layer="transit"', section)
        self.assertNotIn('data-layer="sacred"', section)

    def test_outbound_counter(self):
        page = self.site("go-lodging")
        lodging = self.lodging(page, website="https://example.com/site")
        for _ in range(2):
            response = self.client.get(f"/go/lodging/{lodging.pk}/?from={page.pk}", REMOTE_ADDR="203.0.113.7")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "https://example.com/site")
            self.assertFalse(response.cookies)
        row = LodgingClickDaily.objects.get()
        self.assertEqual((row.lodging_id, row.page_id, row.date, row.count), (lodging.pk, page.pk, date.today(), 2))
        self.assertEqual({f.name for f in LodgingClickDaily._meta.get_fields()},
                         {"id", "lodging", "page", "date", "count"})
        no_link = self.lodging(page, name="No link")
        self.assertEqual(self.client.get(f"/go/lodging/{no_link.pk}/").status_code, 404)


class ExistingMapsUnchangedTests(StayMapTestCase):
    def test_three_pre_v2_maps_keep_their_own_code(self):
        curve = "function radiusFor(z) { return Math.max(2.4, Math.min(7, 2.4 + (z - 2) * 0.62)); }"
        map_page = get_template("home/map_page.html").template.source
        self.assertIn(curve, map_page)
        self.assertIn("map.createPane('sitesPane').style.zIndex = 450;", map_page)
        self.assertIn("L.map(el).setView([20, 0], 2)", map_page)
        trail = get_template("catalog/pilgrimage_trail_page.html").template.source
        self.assertIn("L.map(el, { scrollWheelZoom: false })", trail)
        passport = get_template("pilgrims/profile_detail.html").template.source
        self.assertIn("function radiusFor(z) { return Math.max(5, Math.min(9, 5 + (z - 2) * 0.62)); }", passport)
        for source in (map_page, trail, passport):
            self.assertNotIn("sog-maps.js", source)


class SwitchOffTests(StayMapTestCase):
    @override_settings(SOG_V2_ENABLED="off")
    def test_switch_off_hides_everything(self):
        page = self.site("stay-off")
        lodging = self.lodging(page, website="https://example.com/x")
        self.point(page)
        html = self.html(page)
        self.assertNotIn("stay-map", html)
        self.assertNotIn("Hotel (sample)", html)
        self.assertEqual(self.client.get(f"/go/lodging/{lodging.pk}/").status_code, 404)
        self.assertEqual(LodgingClickDaily.objects.count(), 0)


class ImportSiteMapTests(StayMapTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_file(self, pages):
        path = os.path.join(self.tmpdir, "site_map_test.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"pages": pages}, fh)
        return path

    def run_import(self, path, *flags):
        out = StringIO()
        call_command("import_site_map", path, *flags, stdout=out)
        return out.getvalue()

    def entry(self, page, **extra):
        data = {
            "id": page.pk, "title": page.title, "status": "Ready to import",
            "map_points": [
                {"name": "Main gate (sample)", "kind": "main-entrance", "latitude": 43.0957, "longitude": -0.0531},
                {"name": "Station (sample)", "kind": "Train station", "latitude": "43.1003", "longitude": "-0.0416"},
            ],
            "lodging": [{
                "name": "Hotel (sample)", "kind": "hotel", "latitude": 43.0962, "longitude": -0.0512,
                "nearest_point": "Main gate (sample)", "walk_minutes": 4, "walk_miles": 0.2, "slope": "level",
                "step_free": "yes", "route_geojson": json.loads(ROUTE), "verified_on": "2026-10-01",
            }],
        }
        data.update(extra)
        return data

    def test_dry_run_writes_nothing(self):
        page = self.site("imp-map-dry")
        out = self.run_import(self.write_file([self.entry(page)]), "--dry-run")
        self.assertIn("Would change:  1", out)
        self.assertIn("Map points created:   2", out)
        self.assertEqual(SiteMapPoint.objects.count() + SiteLodging.objects.count(), 0)
        self.assertEqual(page.revisions.count(), 0)

    def test_applies_once_then_reports_zero_changed(self):
        page = self.site("imp-map-twice")
        path = self.write_file([self.entry(page)])
        out = self.run_import(path)
        self.assertIn("Pages changed:  1", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        hotel = page.lodgings.get()
        self.assertEqual((hotel.nearest_point.name, hotel.walk_miles, hotel.verified_on),
                         ("Main gate (sample)", Decimal("0.2"), date(2026, 10, 1)))
        self.assertEqual(page.map_points.get(name="Station (sample)").kind, "train-station")
        self.assertEqual(page.live_revision_id, page.latest_revision_id)
        self.assertEqual(page.live_revision.as_object().lodgings.get().nearest_point_id, hotel.nearest_point_id)
        revisions = page.revisions.count()
        out = self.run_import(path)
        self.assertIn("Pages changed:  0", out)
        self.assertEqual(page.revisions.count(), revisions)
        self.assertIn("Pages matching the file:       1", self.run_import(path, "--verify"))

    def test_a_failed_publish_rolls_back_the_saved_points(self):
        from unittest import mock

        page = self.site("imp-map-rollback")
        with mock.patch("wagtail.models.Revision.publish", side_effect=RuntimeError("publish failed")):
            with self.assertRaises(RuntimeError):
                self.run_import(self.write_file([self.entry(page)]))
        self.assertEqual(SiteMapPoint.objects.count() + SiteLodging.objects.count(), 0)
        self.assertEqual(SacredSitePage.objects.get(pk=page.pk).revisions.count(), 0)

    def test_draft_is_skipped(self):
        page = self.site("imp-map-draft")
        page.save_revision()
        out = self.run_import(self.write_file([self.entry(page)]))
        self.assertIn("unpublished changes", out)
        self.assertEqual(SiteMapPoint.objects.count(), 0)

    def test_conflict_and_bad_values_skip_the_page(self):
        page = self.site("imp-map-conflict")
        self.point(page, name="Main gate (sample)", lat="43.0000")
        out = self.run_import(self.write_file([self.entry(page)]))
        self.assertIn("Conflicts:            1", out)
        self.assertEqual(SiteLodging.objects.count(), 0)
        other = self.site("imp-map-bad")
        bad = self.entry(other)
        bad["lodging"][0]["nearest_point"] = "Station (sample)"
        out = self.run_import(self.write_file([bad]))
        self.assertIn("is not an entrance on this page", out)
        bad = self.entry(other)
        bad["lodging"][0]["route_geojson"] = {"type": "Point", "coordinates": [0, 0]}
        self.assertIn("route_geojson", self.run_import(self.write_file([bad])))
        self.assertEqual(SiteLodging.objects.count(), 0)

    def test_verify_reports_a_mismatch(self):
        page = self.site("imp-map-verify")
        path = self.write_file([self.entry(page)])
        self.run_import(path)
        SiteLodging.objects.filter(page=page).update(walk_minutes=9)
        with self.assertRaises(CommandError):
            call_command("import_site_map", path, "--verify", stdout=StringIO())

    def test_example_file_is_valid_and_matches_nothing(self):
        out = self.run_import(os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "site_map_example.json"),
                              "--dry-run")
        self.assertIn("no SacredSitePage with this id", out)
