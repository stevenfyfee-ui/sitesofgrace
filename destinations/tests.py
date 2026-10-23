"""Phase 4 of Pilgrimage Platform v2: country codes and destination hubs.

Protects: propose/apply of country codes (only approved rows, never
overwriting, drafts skipped, the country text untouched); a hub's curated +
automatic site list; derived saints, trails and tours; empty sections
hidden; the map data holding only live sites; links into hubs (Explore
dropdown, breadcrumb, saint pages, elsewhere-in, trip readiness) only for
live hubs and only with v2 on; and the importer and draft-creation commands.
"""
import csv
import json
import os
import shutil
import tempfile
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from wagtail.models import Page

from catalog.models import PilgrimageTrailPage, SacredSitePage, SaintPage
from catalog.tests_v2_site import V2SiteTestCase
from destinations.models import (
    CombineWith, DestinationHubPage, DestinationIndexPage, HubSite, StayOption,
)
from tours.models import GuidedPilgrimage, TourOperator, TourStop

V2_ON = override_settings(SOG_V2_ENABLED="on")


class HubTestCase(V2SiteTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.index = DestinationIndexPage(title="Destinations", slug="destinations")
        self.site_root().add_child(instance=self.index)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def hub(self, title="Umbria Test", live=True, sites=(), **fields):
        hub = DestinationHubPage(title=title, slug=title.lower().replace(" ", "-"), live=live, **fields)
        hub.hub_sites = [HubSite(site=s, sort_order=i) for i, s in enumerate(sites)]
        self.index.add_child(instance=hub)
        return DestinationHubPage.objects.get(pk=hub.pk)

    def site(self, slug, **kwargs):
        kwargs.setdefault("latitude", Decimal("43.07"))
        kwargs.setdefault("longitude", Decimal("12.61"))
        return self.make_site(slug=slug, **kwargs)


class CountryCodeTests(HubTestCase):
    def test_propose_writes_a_csv_and_changes_nothing(self):
        self.site("c-it", country="Italy")
        self.site("c-it-tomb", country="Italy (tomb)")
        self.site("c-usa", country="USA")
        self.site("c-uk", country="United Kingdom")
        self.site("c-multi", country="France & Spain")
        out = os.path.join(self.tmpdir, "codes.csv")
        call_command("propose_country_codes", "--out", out, stdout=StringIO())
        rows = {r["country"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
        self.assertEqual((rows["Italy"]["proposed_code"], rows["Italy"]["confidence"]), ("IT", "high"))
        self.assertEqual((rows["Italy (tomb)"]["proposed_code"], rows["Italy (tomb)"]["confidence"]), ("IT", "medium"))
        self.assertEqual(rows["USA"]["proposed_code"], "US")
        self.assertEqual((rows["United Kingdom"]["proposed_code"], rows["United Kingdom"]["country_name"]),
                         ("GB", "United Kingdom"))
        self.assertEqual((rows["France & Spain"]["proposed_code"], rows["France & Spain"]["confidence"]), ("", ""))
        self.assertFalse(SacredSitePage.objects.exclude(country_code=None).exists())

    def test_apply_only_approved_rows_skipping_drafts_and_conflicts(self):
        italy = self.site("a-it", country="Italy")
        draft = self.site("a-it-draft", country="Italy")
        draft.save_revision()
        set_already = self.site("a-it-set", country="Italy", country_code="SM")
        usa = self.site("a-usa", country="USA")
        path = os.path.join(self.tmpdir, "apply.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["country", "sites", "proposed_code", "country_name", "confidence", "note", "approved"])
            writer.writerow(["Italy", 3, "IT", "Italy", "high", "", "yes"])
            writer.writerow(["USA", 1, "US", "United States", "high", "", ""])
        out = StringIO()
        call_command("propose_country_codes", "--apply", path, stdout=out)
        italy = SacredSitePage.objects.get(pk=italy.pk)
        self.assertEqual((italy.country_code, italy.country), ("IT", "Italy"))
        self.assertEqual(italy.live_revision_id, italy.latest_revision_id)
        self.assertIsNone(SacredSitePage.objects.get(pk=draft.pk).country_code)
        self.assertEqual(SacredSitePage.objects.get(pk=set_already.pk).country_code, "SM")
        self.assertIsNone(SacredSitePage.objects.get(pk=usa.pk).country_code, "row not approved")
        self.assertIn("Conflicts:            1", out.getvalue())
        self.assertIn("unpublished changes", out.getvalue())
        self.assertEqual(SacredSitePage.objects.get(pk=italy.pk).country_display, "Italy")


class HubSitesTests(HubTestCase):
    def test_curated_first_then_auto(self):
        a = self.site("s-a", title="Zeta Basilica", locality="Assisi", country_code="IT")
        b = self.site("s-b", title="Alpha Shrine", locality="Assisi", country_code="IT")
        c = self.site("s-c", title="Cascia Shrine", locality="Cascia", country_code="IT")
        self.site("s-rome", title="Rome Church", locality="Rome", country_code="IT")
        draft = self.site("s-draft", title="Draft Site", locality="Assisi", country_code="IT")
        draft.unpublish()
        hub = self.hub(sites=[a], include_auto=True, country_codes=["IT"], localities="Assisi\nCascia")
        self.assertEqual([s.title for s in hub.sites], ["Zeta Basilica", "Alpha Shrine", "Cascia Shrine"])
        curated_only = self.hub(title="Curated Only", sites=[c, a], include_auto=False, localities="Assisi")
        self.assertEqual([s.title for s in curated_only.sites], ["Cascia Shrine", "Zeta Basilica"])
        whole_country = self.hub(title="All Italy", include_auto=True, country_codes=["IT"])
        self.assertEqual(len(whole_country.sites), 4)
        self.assertNotIn(b.pk, [s.pk for s in self.hub(title="Nothing").sites])

    def test_map_data_has_only_live_sites_with_coordinates(self):
        live = self.site("m-live", title="Live Site")
        no_coords = self.make_site(slug="m-nocoords", title="No Coords")
        hidden = self.site("m-hidden", title="Hidden Site")
        hidden.unpublish()
        hub = self.hub(sites=[live, no_coords, hidden])
        data = hub.map_payload()
        self.assertEqual([d["title"] for d in data], ["Live Site"])
        html = self.client.get(hub.url).content.decode()
        payload = json.loads(html.split('id="hub-map-data" type="application/json">')[1].split("</script>")[0])
        self.assertEqual([d["title"] for d in payload], ["Live Site"])
        self.assertIn("/static/vendor/leaflet-1.9.4/leaflet.js", html)
        self.assertIn("js/sog-maps.js", html)
        self.assertNotIn("unpkg.com", html)


class DerivedSectionsTests(HubTestCase):
    def test_saints_trails_and_tours_are_derived(self):
        francis = SaintPage(title="St. Francis Test", slug="francis-test")
        clare = SaintPage(title="St. Clare Test", slug="clare-test")
        for saint in (francis, clare):
            self.site_root().add_child(instance=saint)
        a = self.site("d-a", associated_saint=francis)
        b = self.site("d-b", associated_saint=francis)
        c = self.site("d-c", associated_saint=clare)
        trail = PilgrimageTrailPage(title="Footsteps Test", slug="footsteps-test")
        self.site_root().add_child(instance=trail)
        operator = TourOperator.objects.create(name="Op (sample)")
        tour = GuidedPilgrimage(title="Umbria Tour (sample)", operator=operator, is_live=True,
                                booking_url="https://example.com/t", duration_days=9)
        tour.stops = [TourStop(site=c)]
        tour.save()
        hidden = GuidedPilgrimage(title="Hidden tour", operator=operator, is_live=False)
        hidden.stops = [TourStop(site=a)]
        hidden.save()
        hub = self.hub(sites=[a, b, c])
        hub.related_trails = [trail]
        hub.save()
        hub = DestinationHubPage.objects.get(pk=hub.pk)
        self.assertEqual([s.title for s in hub.saints], ["St. Francis Test", "St. Clare Test"])
        self.assertEqual([t.title for t in hub.trails], ["Footsteps Test"])
        self.assertEqual([t.title for t in hub.tours], ["Umbria Tour (sample)"])
        html = self.client.get(hub.url).content.decode()
        self.assertIn('href="#go-deeper">Guided pilgrimages</a>', html)
        self.assertIn("Umbria Tour (sample)", html)
        self.assertIn(f'/go/tour/{tour.pk}/?from={hub.pk}"', html)
        self.assertIn("Some pilgrimage-tour links on this page", html)
        self.assertIn("Footsteps Test", html)

    def test_empty_sections_hide(self):
        hub = self.hub(title="Empty Hub")
        html = self.client.get(hub.url).content.decode()
        for needle in ('id="hubMap"', 'id="stay"', 'id="sites"', 'id="day-trips"', 'id="local-travel"',
                       'id="go-deeper"', "Guided pilgrimages</a>"):
            self.assertNotIn(needle, html)
        self.assertIn('href="/plan/">Plan a trip here</a>', html)

    def test_day_trip_sites_are_not_repeated_in_major_sites(self):
        curated = self.site("dd-curated", title="Curated Basilica", locality="Assisi")
        auto = self.site("dd-auto", title="Auto Shrine", locality="Assisi")
        trip_site = self.site("dd-trip", title="Day Trip Shrine", locality="Assisi")
        hub = self.hub(title="Dedupe Hub", sites=[curated], include_auto=True, localities="Assisi")
        hub.combine_with = [CombineWith(site=trip_site, reason="Worth the drive", travel_time="1 h", mode="drive")]
        hub.save_revision().publish()
        hub = DestinationHubPage.objects.get(pk=hub.pk)
        self.assertEqual([s.title for s in hub.major_sites], ["Curated Basilica", "Auto Shrine"])
        self.assertIn("Day Trip Shrine", [s.title for s in hub.sites], "still on the map")
        html = self.client.get(hub.url).content.decode()
        sites_section = html.split('id="sites"')[1].split("</section>")[0]
        self.assertNotIn("Day Trip Shrine", sites_section)
        self.assertIn("Day Trip Shrine", html.split('id="day-trips"')[1].split("</section>")[0])

    def test_major_sites_cap_at_twelve(self):
        sites = [self.site(f"cap-{i}", title=f"Site {i:02d}", locality="Capville") for i in range(14)]
        hub = self.hub(title="Cap Hub", sites=sites[:3], include_auto=True, localities="Capville")
        titles = [s.title for s in hub.major_sites]
        self.assertEqual(len(titles), 12)
        self.assertEqual(titles[:3], ["Site 00", "Site 01", "Site 02"])

    def test_sections_render_when_filled(self):
        site = self.site("f-site", title="Filled Site", summary_short="One line.")
        hub = self.hub(title="Filled Hub", sites=[site], getting_around="<p>Take the bus.</p>",
                       plan_link_url="/plan/?site=f-site")
        hub.stay_options = [StayOption(label="1 day", text="Short visit.")]
        hub.combine_with = [CombineWith(name="Norcia", reason="Birthplace of St. Benedict", travel_time="1 h 40",
                                        mode="drive")]
        hub.save_revision().publish()
        html = self.client.get(hub.url).content.decode()
        for needle in ('id="hubMap"', "Suggested lengths of stay", "Major sacred sites", "One line.",
                       "Day trips from Filled Hub", "1 h 40 drive", "Take the bus.", 'href="/plan/?site=f-site"'):
            self.assertIn(needle, html)
        self.assertNotIn('id="go-deeper"', html)


class LinkingTests(HubTestCase):
    def setUp(self):
        super().setUp()
        from home.models import StandardPage
        from wagtailmenus.models import MainMenu, MainMenuItem

        explore = StandardPage(title="Explore", slug="explore", show_in_menus=True)
        self.site_root().add_child(instance=explore)
        explore.add_child(instance=StandardPage(title="Marian Apparitions", slug="marian-test", show_in_menus=True))
        menu = MainMenu.get_for_site(self.site_root().get_site())
        MainMenuItem.objects.create(menu=menu, link_page=explore, allow_subnav=True, sort_order=1)
        self.member = self.site("l-member", title="Member Site", country="Italy")
        saint = SaintPage(title="St. Linked", slug="st-linked")
        self.site_root().add_child(instance=saint)
        self.saint = saint
        SacredSitePage.objects.filter(pk=self.member.pk).update(associated_saint=saint)
        self.member = SacredSitePage.objects.get(pk=self.member.pk)

    @V2_ON
    def test_links_only_for_live_hubs(self):
        self.hub(title="Draft Hub", live=False, sites=[self.member])
        html = self.html(self.member)
        self.assertNotIn("Draft Hub", html)
        self.assertNotIn("More in", html)
        self.hub(title="Live Hub", sites=[self.member], travel_advisory_url="https://example.com/advisory")
        html = self.html(self.member)
        self.assertIn('<li class="nav-item nav-group-label" aria-hidden="true">By destination</li>', html)
        self.assertIn(">Live Hub</a></li>", html)
        self.assertNotIn("Draft Hub", html)
        self.assertIn("All destinations →", html)
        self.assertIn('v2-crumb-hub">More in <a href="/destinations/live-hub/">Live Hub</a>', html)
        saint_html = self.client.get(SaintPage.objects.get(pk=self.saint.pk).url).content.decode()
        self.assertIn('Visit in <a href="/destinations/live-hub/">Live Hub</a>', saint_html)

    @V2_ON
    def test_trip_readiness_uses_the_hub_advisory(self):
        SacredSitePage.objects.filter(pk=self.member.pk).update(prep_prayer="<p>Pray.</p>")
        self.hub(title="Advisory Hub", sites=[self.member], travel_advisory_url="https://example.com/advisory")
        html = self.html(self.member)
        self.assertIn('href="https://example.com/advisory" target="_blank" rel="noopener">travel information for Advisory Hub', html)

    @V2_ON
    def test_elsewhere_prefers_the_hub(self):
        other = self.site("l-other", title="Other Hub Site", country="Italy")
        operator = TourOperator.objects.create(name="Op")
        tour = GuidedPilgrimage(title="Hub Other Tour", operator=operator, is_live=True,
                                booking_url="https://example.com/x")
        tour.stops = [TourStop(site=other)]
        tour.save()
        self.hub(title="Elsewhere Hub", sites=[self.member, other])
        html = self.html(self.member)
        self.assertIn("Guided pilgrimages elsewhere in Elsewhere Hub", html)
        self.assertIn("Hub Other Tour", html)

    def test_switch_off_leaves_menu_and_breadcrumbs_alone(self):
        self.hub(title="Live Hub", sites=[self.member])
        with override_settings(SOG_V2_ENABLED="off"):
            html = self.html(self.member)
            saint_html = self.client.get(SaintPage.objects.get(pk=self.saint.pk).url).content.decode()
        self.assertNotIn("By destination", html)
        self.assertNotIn("Live Hub", html)
        self.assertNotIn("More in", html)
        self.assertNotIn("Visit in", saint_html)
        self.assertIn("Marian Apparitions", html, "the database menu itself still renders")


class CommandTests(HubTestCase):
    def test_create_destination_hubs_makes_unpublished_drafts_once(self):
        DestinationIndexPage.objects.all().delete()
        call_command("create_destination_hubs", stdout=StringIO())
        call_command("create_destination_hubs", stdout=StringIO())
        hubs = DestinationHubPage.objects.order_by("path")
        self.assertEqual([h.title for h in hubs],
                         ["Rome & Vatican City", "Assisi & Umbria", "Paris & Northern France", "Portugal"])
        self.assertFalse(any(h.live for h in hubs))
        self.assertFalse(DestinationIndexPage.objects.get().live)
        self.assertFalse(any(h.intro for h in hubs), "titles only")

    def write(self, pages):
        path = os.path.join(self.tmpdir, "hubs_test.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"pages": pages}, fh)
        return path

    def test_import_hubs_dry_run_draft_revision_idempotent_and_conflict(self):
        site = self.site("i-site")
        hub = self.hub(title="Import Hub", live=False)
        entry = {"id": hub.pk, "title": "Import Hub", "status": "Ready to import",
                 "fields": {"intro": "Hello.", "country_codes": ["it"], "localities": ["Assisi"],
                            "include_auto": True},
                 "hub_sites": [site.pk], "stay_options": [{"label": "1 day", "text": "Short."}]}
        path = self.write([entry])
        out = StringIO()
        call_command("import_hubs", path, "--dry-run", stdout=out)
        self.assertIn("Would change:   1", out.getvalue())
        self.assertFalse(DestinationHubPage.objects.get(pk=hub.pk).get_latest_revision_as_object().intro)
        call_command("import_hubs", path, stdout=StringIO())
        hub = DestinationHubPage.objects.get(pk=hub.pk)
        self.assertFalse(hub.live, "a draft hub stays unpublished")
        draft = hub.get_latest_revision_as_object()
        self.assertEqual((draft.intro, draft.country_codes, draft.localities), ("Hello.", ["IT"], "Assisi"))
        self.assertEqual([r.site_id for r in draft.hub_sites.all()], [site.pk])
        revisions = hub.revisions.count()
        out = StringIO()
        call_command("import_hubs", path, stdout=out)
        self.assertIn("Hubs changed:   0", out.getvalue())
        self.assertEqual(hub.revisions.count(), revisions)
        call_command("import_hubs", path, "--verify", stdout=StringIO())
        entry["fields"]["intro"] = "Something else."
        out = StringIO()
        call_command("import_hubs", self.write([entry]), stdout=out)
        self.assertIn("Conflicts:            1", out.getvalue())

    def test_import_hubs_skips_a_live_hub_with_a_draft(self):
        hub = self.hub(title="Busy Hub")
        hub.save_revision()
        out = StringIO()
        call_command("import_hubs", self.write([{"id": hub.pk, "title": "Busy Hub", "status": "Ready to import",
                                                  "fields": {"intro": "x"}}]), stdout=out)
        self.assertIn("unpublished changes", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("import_hubs", self.write([{"id": hub.pk, "title": "Busy Hub", "status": "Ready to import",
                                                      "fields": {"intro": "x"}}]), "--verify", stdout=StringIO())
