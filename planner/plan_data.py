"""Load the itinerary engine's inputs from the database.

Kept apart from planner/itinerary.py so the engine stays pure. Only live
sites are ever passed on: a curated row that links a page which has since
been unpublished simply leaves that site out.
"""
from decimal import Decimal

from planner.itinerary import DestinationData, PlanDayRef, Pricing, SiteRef
from planner.models import CalculatorDefaults, DestinationCost, DestinationPlanDay, RegionFlightAssumption


def _f(value):
    return None if value is None else float(value)


def site_ref(page, request=None):
    return SiteRef(slug=page.slug, title=page.title, url=page.get_url(request) or "",
                   latitude=_f(page.latitude), longitude=_f(page.longitude), pk=page.pk)


def load_pricing(request=None):
    d = CalculatorDefaults.load(request_or_site=request)
    return Pricing(
        meals_per_day=d.meals_per_day,
        people_per_room=max(1, d.people_per_room),
        multipliers={"budget": d.hotel_tier_budget_multiplier, "mid": d.hotel_tier_midrange_multiplier,
                     "comfort": d.hotel_tier_comfort_multiplier},
        misc_pct=d.misc_buffer_percent,
        hop=Decimal(d.inter_destination_hop_usd),
        region_flights={r.region: r.avg_roundtrip_usd_from_us for r in RegionFlightAssumption.objects.all()},
        currency=d.currency,
    )


def destination_data(dest, request=None):
    """One DestinationCost as engine input (its plan_days and live sites)."""
    through = DestinationPlanDay.sites.through
    curated = []
    for day in dest.plan_days.all().order_by("sort_order"):
        links = (through.objects.filter(destinationplanday=day, sacredsitepage__live=True)
                 .select_related("sacredsitepage").order_by("id"))
        curated.append(PlanDayRef(title=day.title, sites=[site_ref(l.sacredsitepage, request) for l in links],
                                  extra_places=day.extra_places or ""))
    sites = [site_ref(p, request) for p in dest.associated_sites.live().order_by("title", "pk")]
    return DestinationData(
        slug=dest.slug, city=dest.city, region=dest.region, country=dest.country,
        latitude=_f(dest.latitude), longitude=_f(dest.longitude),
        airport_iata=dest.nearest_airport_iata or "", airport_name=dest.nearest_airport_name or "",
        gateway_iata=dest.gateway_airport_iata or "", gateway_name=dest.gateway_airport_name or "",
        hotel=dest.hotel_night_usd, meal=dest.meal_usd, transport=dest.local_transport_day_usd,
        curated=curated, sites=sites,
    )


def load_destinations(slugs, request=None):
    """{slug: DestinationData} for the slugs that exist."""
    found = DestinationCost.objects.filter(slug__in=list(slugs))
    return {d.slug: destination_data(d, request) for d in found}
