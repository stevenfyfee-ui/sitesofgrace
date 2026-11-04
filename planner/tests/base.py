"""Shared fixtures for the planner tests. Every value here is made up for the
tests; nothing comes from the live database. Costs for Rome / Vatican City
and Assisi copy today's seed values so the golden budget test matches the
old estimator."""
from datetime import date
from decimal import Decimal

from wagtail.models import Site

from catalog.tests import SacredSitePageTestCase
from home.models import LegalPage
from planner.models import (
    CalculatorDefaults, DestinationCost, DestinationPlanDay, RegionFlightAssumption,
)

SEED = {
    "rome-vatican-city": dict(
        city="Rome / Vatican City", country="Italy", region="Southern Europe",
        latitude=Decimal("41.902200"), longitude=Decimal("12.453900"),
        nearest_airport_iata="FCO", nearest_airport_name="Rome Fiumicino",
        hotel_night_usd=Decimal("130"), meal_usd=Decimal("22"),
        local_transport_day_usd=Decimal("8"), taxi_typical_usd=Decimal("18"),
    ),
    "assisi": dict(
        city="Assisi", country="Italy", region="Southern Europe",
        latitude=Decimal("43.070300"), longitude=Decimal("12.619600"),
        nearest_airport_iata="PEG", nearest_airport_name="Perugia",
        gateway_airport_iata="FCO", gateway_airport_name="Rome Fiumicino",
        hotel_night_usd=Decimal("100"), meal_usd=Decimal("20"),
        local_transport_day_usd=Decimal("6"), taxi_typical_usd=Decimal("15"),
    ),
    "lourdes": dict(
        city="Lourdes", country="France", region="Western Europe",
        latitude=Decimal("43.094900"), longitude=Decimal("-0.046000"),
        nearest_airport_iata="LDE", nearest_airport_name="Tarbes-Lourdes",
        hotel_night_usd=Decimal("110"), meal_usd=Decimal("20"),
        local_transport_day_usd=Decimal("5"), taxi_typical_usd=Decimal("15"),
    ),
}


class PlannerTestCase(SacredSitePageTestCase):
    def setUp(self):
        # Other apps' tests create extra Sites; Wagtail caches site root paths
        # process-wide, and a stale cache turns page.url into None here.
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        super().setUp()

    def seed_costs(self):
        defaults = CalculatorDefaults.load()
        defaults.meals_per_day = 3
        defaults.people_per_room = 2
        defaults.hotel_tier_budget_multiplier = Decimal("0.70")
        defaults.hotel_tier_midrange_multiplier = Decimal("1.00")
        defaults.hotel_tier_comfort_multiplier = Decimal("1.60")
        defaults.misc_buffer_percent = 12
        defaults.inter_destination_hop_usd = Decimal("150")
        defaults.save()
        for region, usd in (("Southern Europe", 850), ("Western Europe", 800)):
            RegionFlightAssumption.objects.update_or_create(
                region=region, defaults={"avg_roundtrip_usd_from_us": Decimal(usd)},
            )

    def make_destination(self, slug, **overrides):
        values = {**SEED.get(slug, dict(city=slug.title(), region="Southern Europe")), **overrides}
        return DestinationCost.objects.create(slug=slug, **values)

    def make_site(self, slug="test-site", **kwargs):
        kwargs.setdefault("title", slug.replace("-", " ").title())
        return super().make_site(slug=slug, **kwargs)

    def add_day(self, dest, order, title, sites=(), extra=None):
        day = DestinationPlanDay.objects.create(destination=dest, sort_order=order - 1, title=title,
                                                extra_places=extra)
        through = DestinationPlanDay.sites.through
        for site in sites:
            through.objects.create(destinationplanday=day, sacredsitepage=site)
        return day

    def publish_disclosure(self, live=True):
        page = LegalPage(title="Affiliate Disclosure", slug="affiliate-disclosure",
                         effective_date=date(2026, 10, 1), body="<p>Disclosure.</p>", live=live)
        self.site_root().add_child(instance=page)
        return page

    def make_plan_page(self):
        from planner.models import PlanPage

        page = PlanPage(title="Plan your pilgrimage", slug="plan", heading="Plan your pilgrimage")
        self.site_root().add_child(instance=page)
        return page
