"""With SOG_PLANNER_V2 off, /plan/ must be byte-identical to main.

The golden files in planner/tests/golden/ were rendered by this same test
file on origin/main (before Trip Planner v2), with:

    PLANNER_WRITE_GOLDEN=1 python manage.py test planner.tests.test_flag_off

That's why this file imports nothing that main doesn't have, and builds its
fixture from fields main already had, with fixed primary keys. Two things
are normalized on both sides before comparing: the per-request CSRF token,
and hashed static filenames (site.124697dd488a.css -> site.HASH.css), so an
unrelated CSS or JS change on main doesn't break this test. How to
regenerate the saved copies after merging main: docs/planner/flag-off-golden.md.
"""
import os
import re
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import override_settings
from wagtail.models import Site

from catalog.tests import SacredSitePageTestCase
from pilgrims.models import SiteVisit
from planner.models import CalculatorDefaults, DestinationCost, PlanPage, RegionFlightAssumption

GOLDEN = Path(__file__).parent / "golden"
WRITE = os.environ.get("PLANNER_WRITE_GOLDEN") == "1"
CSRF_RE = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+(")')
HASHED_STATIC_RE = re.compile(r"\.[0-9a-f]{12}(\.(?:css|js|mjs|map|svg|png|jpe?g|webp|gif|ico|woff2?|ttf|otf))\b")


def normalize(html):
    html = CSRF_RE.sub(r"\1CSRF\2", html)
    return HASHED_STATIC_RE.sub(r".HASH\1", html)


class FlagOffByteIdenticalTests(SacredSitePageTestCase):
    def setUp(self):
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        super().setUp()
        defaults = CalculatorDefaults.load()
        defaults.inter_destination_hop_usd = Decimal("150")
        defaults.save()
        RegionFlightAssumption.objects.create(region="Southern Europe", avg_roundtrip_usd_from_us=Decimal("850"))
        DestinationCost.objects.create(
            pk=9001, city="Rome / Vatican City", country="Italy", region="Southern Europe",
            nearest_airport_iata="FCO", nearest_airport_name="Rome Fiumicino",
            hotel_night_usd=Decimal("130"), meal_usd=Decimal("22"),
            local_transport_day_usd=Decimal("8"), taxi_typical_usd=Decimal("18"),
        )
        DestinationCost.objects.create(
            pk=9002, city="Assisi", country="Italy", region="Southern Europe",
            nearest_airport_iata="PEG", nearest_airport_name="Perugia",
            hotel_night_usd=Decimal("100"), meal_usd=Decimal("20"),
            local_transport_day_usd=Decimal("6"), taxi_typical_usd=Decimal("15"),
        )
        self.site_page = self.make_site("basilica-of-st-francis", title="Basilica of St. Francis", locality="Assisi")
        self.site_root().add_child(instance=PlanPage(
            title="Plan your pilgrimage", slug="plan", heading="Plan your pilgrimage",
            intro="<p>Estimate the cost of a trip.</p>",
        ))

    def check(self, name, path):
        html = normalize(self.client.get(path).content.decode())
        golden = GOLDEN / f"{name}.html"
        if WRITE:
            GOLDEN.mkdir(exist_ok=True)
            golden.write_text(html, encoding="utf-8", newline="\n")
            return
        self.assertTrue(golden.exists(), f"{golden} is missing; render it on origin/main")
        self.assertEqual(html, normalize(golden.read_text(encoding="utf-8")))

    @override_settings(SOG_PLANNER_V2="off")
    def test_signed_out(self):
        self.check("plan_signed_out", "/plan/")

    @override_settings(SOG_PLANNER_V2="off")
    def test_site_preselect(self):
        self.check("plan_site_preselect", "/plan/?site=basilica-of-st-francis")

    @override_settings(SOG_PLANNER_V2="off")
    def test_signed_in_with_journey(self):
        user = get_user_model().objects.create_user("johndoe", "john@example.com", "pw")
        SiteVisit.objects.create(owner=user, site=self.site_page, status="visited")
        self.client.force_login(user)
        self.check("plan_signed_in_journey", "/plan/")

    @override_settings(SOG_PLANNER_V2="off", SOG_V2_ENABLED="on")
    def test_signed_out_with_site_v2_on(self):
        """The planner switch is separate: the rest of v2 being on changes nothing here."""
        self.check("plan_signed_out_v2_on", "/plan/")


class NormalizeTests(SacredSitePageTestCase):
    def test_hashed_static_names_and_csrf(self):
        self.assertEqual(
            normalize('<link href="/static/css/site.124697dd488a.css"><script src="/static/js/a.0123456789ab.js">'
                      '<input name="csrfmiddlewaretoken" value="abc123">'),
            '<link href="/static/css/site.HASH.css"><script src="/static/js/a.HASH.js">'
            '<input name="csrfmiddlewaretoken" value="CSRF">',
        )
        self.assertEqual(normalize("/static/css/site.css"), "/static/css/site.css")
