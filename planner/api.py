"""JSON for the Trip Planner v2 page: /plan/build/ and /plan/search/.

Both are routes on PlanPage (planner/models.py), exist only while
SOG_PLANNER_V2 allows them for the request, and are rate-limited per hashed
IP with core.ratelimit (there's no user to count against when signed out).
"""
from django.db.models import Q
from django.http import JsonResponse
from django.utils.cache import patch_cache_control

from catalog.models import SacredSitePage
from core import ratelimit
from core.v2 import planner_v2_mode
from planner.geo import haversine_miles, locality_matches
from planner.itinerary import (
    DestinationData, build_itinerary, default_nights, itinerary_json, round_half_up,
)
from planner.models import CalculatorDefaults, DestinationCost, PlannerSettings
from planner.plan_data import load_destinations, load_pricing
from planner.urlstate import parse_state

NEAR_ROUTE_MILES = 150
SEARCH_MIN_CHARS = 2
SEARCH_MAX_RESULTS = 8
BUILD_LIMIT, SEARCH_LIMIT, WINDOW_SECONDS = 120, 120, 60


def destination_for_site(site):
    """A SacredSitePage's planner destination: the explicit associated_sites
    link first, then the site's locality against the destination city (equal,
    then either containing the other). None if nothing matches."""
    dc = DestinationCost.objects.filter(associated_sites=site).first()
    if dc:
        return dc
    locality = (getattr(site, "locality", "") or "").strip()
    if locality:
        dc = DestinationCost.objects.filter(city__iexact=locality).first()
        if dc:
            return dc
        for cand in DestinationCost.objects.all():
            if locality_matches(locality, cand.city):
                return cand
    return None


def rate_limited(request, prefix, limit):
    from pilgrims.views import _ip_hash

    return ratelimit.hit(prefix, _ip_hash(request), limit, WINDOW_SECONDS)


def too_many():
    return JsonResponse({"error": "rate_limited", "message": "Too many requests. Try again in a minute."},
                        status=429)


def cacheable(response, max_age=300):
    """Public only when the switch is fully on, so a shared cache never hands
    a staff-only answer to the public."""
    if planner_v2_mode() == "on":
        patch_cache_control(response, public=True, max_age=max_age)
    else:
        patch_cache_control(response, private=True, max_age=max_age)
    return response


def near_route(stops, candidates, limit_miles=NEAR_ROUTE_MILES):
    """The nearest destination not already in the trip, within limit_miles
    of any stop: (destination, whole miles, from stop) or None. Destinations
    without coordinates are never suggested."""
    chosen = {d.slug for d in stops}
    best = None
    for stop in stops:
        if not stop.has_coords:
            continue
        for cand in candidates:
            if cand.slug in chosen or cand.latitude is None or cand.longitude is None:
                continue
            miles = haversine_miles(stop.latitude, stop.longitude, cand.latitude, cand.longitude)
            if miles <= limit_miles and (best is None or (miles, cand.city) < (best[1], best[0].city)):
                best = (cand, miles, stop)
    if best is None:
        return None
    return best[0], round_half_up(best[1]), best[2]


def stop_summary(dest, nights, index, pace):
    sites_count = (len({s.pk or s.slug for d in dest.curated for s in d.sites}) if dest.curated
                   else len(dest.sites))
    return {
        "slug": dest.slug, "city": dest.city, "short": dest.short_name, "nights": nights,
        "plan_kind": dest.plan_kind, "curated_days": len(dest.curated), "sites": sites_count,
        "fly_iata": dest.fly_iata, "nearest_iata": dest.nearest_iata_if_different,
        "default_nights": default_nights(dest, index == 0, pace),
    }


NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
                9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}


def journey_destinations(user):
    """Destinations of the sites on a signed-in pilgrim's journey, first seen
    first (the old planner's "From your journey" preselect)."""
    if not getattr(user, "is_authenticated", False):
        return []
    from pilgrims.models import SiteVisit

    seen, out = set(), []
    # Ordered explicitly: without it the rows come back in storage order,
    # which drifts from creation order once rows are removed and space reused.
    visits = SiteVisit.objects.filter(owner=user).select_related("site").order_by("created_at", "pk")
    for visit in visits:
        dc = destination_for_site(visit.site)
        if dc and dc.slug not in seen:
            seen.add(dc.slug)
            out.append(dc)
    return out


def _add_stop(state, slug, max_stops, request, first=False):
    """Add a destination with its default nights. Returns a message, or ""."""
    data = load_destinations([slug], request).get(slug)
    if data is None:
        return ""
    if any(s == slug for s, _ in state.stops):
        return f"{data.city} is already in your plan."
    if len(state.stops) >= max_stops:
        return (f"{NUMBER_WORDS.get(max_stops, max_stops)} stop{'s' if max_stops != 1 else ''} "
                f"is the most a plan can hold.")
    nights = default_nights(data, first or not state.stops, state.pace)
    if first:
        state.stops.insert(0, (slug, nights))
    else:
        state.stops.append((slug, nights))
    return ""


def build_plan(request, params, max_stops=None, user=None):
    """Everything the page needs for one plan state. Used by /plan/build/ and
    by the server-rendered page, so both always agree.

    Besides the URL state (planner/urlstate.py) it understands:
    site=<sacred site slug>  that site's destination becomes the first stop
                             ("Added from <site>"); a live site with no
                             destination is reported as not plannable yet
    add=<destination slug>   append it with its default nights
    and, for a signed-in user with an empty plan, preselects the first
    destination on their journey.
    """
    settings = PlannerSettings.load(request_or_site=request)
    max_stops = max_stops or settings.max_stops
    all_dests = list(DestinationCost.objects.all())
    state = parse_state(params, {d.slug for d in all_dests}, max_stops,
                        default_party=CalculatorDefaults.load(request_or_site=request).default_party_size)
    messages, added_from, unplannable = [], None, None

    site_slug = (params.get("site") or "").strip()
    if site_slug:
        site = SacredSitePage.objects.live().filter(slug=site_slug).first()
        if site:
            dest = destination_for_site(site)
            if dest:
                added_from = site
                if not any(s == dest.slug for s, _ in state.stops):
                    if len(state.stops) >= max_stops:
                        state.stops.pop()
                    _add_stop(state, dest.slug, max_stops, request, first=True)
            else:
                unplannable = site

    add_slug = (params.get("add") or "").strip().lower()
    if add_slug:
        message = _add_stop(state, add_slug, max_stops, request)
        if message:
            messages.append(message)

    journey = journey_destinations(user) if user is not None else []
    if not state.stops and not site_slug and not add_slug and not params.get("t") and journey:
        _add_stop(state, journey[0].slug, max_stops, request)

    data = load_destinations([s for s, _ in state.stops], request)
    stops = [(data[slug], n) for slug, n in state.stops if slug in data]
    pricing = load_pricing(request)
    itinerary = build_itinerary(stops, state.start_date, state.party, state.tier, state.pace, pricing=pricing)
    near = None
    if len(stops) < max_stops:
        candidates = [DestinationData(slug=d.slug, city=d.city, region=d.region,
                                      latitude=None if d.latitude is None else float(d.latitude),
                                      longitude=None if d.longitude is None else float(d.longitude))
                      for d in all_dests]
        near = near_route([d for d, _ in stops], candidates)
    return {
        "state": state, "stops": stops, "itinerary": itinerary, "pricing": pricing,
        "near": near, "max_stops": max_stops, "messages": messages,
        "added_from": added_from, "unplannable": unplannable, "journey": journey,
        "all_dests": all_dests,
    }


def plan_json(plan):
    state, near = plan["state"], plan["near"]
    return {
        "query": state.query(),
        "state": {"stops": [{"slug": s, "nights": n} for s, n in state.stops],
                  "start_date": state.start_date.isoformat() if state.start_date else None,
                  "party": state.party, "tier": state.tier, "pace": state.pace},
        "stops": [stop_summary(d, n, i, state.pace) for i, (d, n) in enumerate(plan["stops"])],
        "itinerary": itinerary_json(plan["itinerary"], plan["pricing"].currency),
        "near": ({"slug": near[0].slug, "city": near[0].city, "short": near[0].short_name, "miles": near[1],
                  "from": near[2].short_name} if near else None),
        "max_stops": plan["max_stops"],
        "messages": plan["messages"],
    }


def build_json(request):
    if rate_limited(request, "planner-build", BUILD_LIMIT):
        return too_many()
    from planner.page import build_with_fragments

    return cacheable(JsonResponse(build_with_fragments(request)))


def search(q, limit=SEARCH_MAX_RESULTS):
    """Destinations first, then live sacred sites that add a destination,
    then sites that are "not plannable yet" (no destination)."""
    q = (q or "").strip()
    if len(q) < SEARCH_MIN_CHARS:
        return []
    results = []
    for d in DestinationCost.objects.filter(Q(city__icontains=q) | Q(country__icontains=q)).order_by("city")[:limit]:
        results.append({"kind": "destination", "label": d.city, "sub": d.country, "dest": d.slug,
                        "dest_city": d.city})
    room = limit - len(results)
    if room > 0:
        # Look a little further than needed so plannable sites aren't crowded
        # out by unplannable ones that sort earlier by title.
        sites = (SacredSitePage.objects.live()
                 .filter(Q(title__icontains=q) | Q(locality__icontains=q) | Q(country__icontains=q))
                 .order_by("title")[:room * 3])
        found = []
        for site in sites:
            dest = destination_for_site(site)
            found.append({
                "kind": "site", "label": site.title,
                "sub": ", ".join(p for p in (site.locality, site.country) if p),
                "slug": site.slug, "url": site.url or "",
                "dest": dest.slug if dest else None, "dest_city": dest.city if dest else None,
            })
        found.sort(key=lambda r: r["dest"] is None)  # stable: title order kept within each group
        results += found[:room]
    return results


def search_json(request):
    if rate_limited(request, "planner-search", SEARCH_LIMIT):
        return too_many()
    return cacheable(JsonResponse({"results": search(request.GET.get("q"))}))
