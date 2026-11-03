"""Trip Planner v2 page: context and the fragments it shares with /plan/build/.

The page is rendered on the server from the query string, so a shared link
works without JavaScript. Every control is a real link or GET form carrying
the whole plan; planner/static/planner/js/plan-v2.js takes them over, calls
/plan/build/ and swaps in the same fragments rendered here.
"""
from dataclasses import replace
from urllib.parse import quote

from django.template.loader import render_to_string
from django.urls import reverse

from planner.api import NUMBER_WORDS, build_plan, plan_json
from planner.api import search as run_search
from planner.booking import affiliate_disclosure_url, booking_links_allowed
from planner.itinerary import TIER_LABELS, money
from planner.models import NIGHTS_MAX, NIGHTS_MIN, PARTY_MAX, PACE_CHOICES, PlannerBookingLink

POPULAR = ["lourdes", "fatima", "rome-vatican-city", "assisi", "medjugorje", "jerusalem"]
JOURNEY_CHIPS_MAX = 4
CUT_ROWS_SHOWN = 2
FRAGMENTS = {
    "stops": "planner/v2/_stops.html",
    "days": "planner/v2/_days.html",
    "route": "planner/v2/_route.html",
    "budget": "planner/v2/_budget.html",
    "mbar": "planner/v2/_mbar_total.html",
}


def _q(state, **changes):
    return "?" + replace(state, **changes).query()


def stop_controls(state):
    """For each stop, the plan URL after each control: nights -/+, earlier,
    later, remove. None where the control doesn't apply."""
    out = []
    stops = state.stops
    for i, (slug, n) in enumerate(stops):
        def with_stops(new):
            return _q(state, stops=new)

        swapped_up = stops[:i - 1] + [stops[i], stops[i - 1]] + stops[i + 1:] if i > 0 else None
        swapped_down = stops[:i] + [stops[i + 1], stops[i]] + stops[i + 2:] if i < len(stops) - 1 else None
        out.append({
            "dec": with_stops(stops[:i] + [(slug, n - 1)] + stops[i + 1:]) if n > NIGHTS_MIN else None,
            "inc": with_stops(stops[:i] + [(slug, n + 1)] + stops[i + 1:]) if n < NIGHTS_MAX else None,
            "up": with_stops(swapped_up) if swapped_up else None,
            "down": with_stops(swapped_down) if swapped_down else None,
            "remove": with_stops(stops[:i] + stops[i + 1:]),
        })
    return out


def distinct_sites(dest):
    """How many different sacred places a stop covers (a site on two curated
    days counts once)."""
    if dest.curated:
        return len({s.pk or s.slug for day in dest.curated for s in day.sites})
    return len(dest.sites)


def journey_chips(plan):
    """"From your journey": destinations not already in the plan, at most 4."""
    chosen = {s for s, _ in plan["state"].stops}
    return [d for d in plan["journey"] if d.slug not in chosen][:JOURNEY_CHIPS_MAX]


def fragment_context(request, plan):
    state, it = plan["state"], plan["itinerary"]
    currency = plan["pricing"].currency
    b = it.budget
    controls = stop_controls(state)
    stops = []
    for i, (dest, nights) in enumerate(plan["stops"]):
        sites = distinct_sites(dest)
        stops.append({"index": i, "number": i + 1, "dest": dest, "nights": nights, "sites": sites,
                      "controls": controls[i], "first": i == 0, "last": i == len(plan["stops"]) - 1})
    groups, current = [], None
    for day in it.days:
        if day.kind == "departure":
            break
        if current is None or current["slug"] != day.stop_slug:
            dest, nights = next((d, n) for d, n in plan["stops"] if d.slug == day.stop_slug)
            current = {"slug": day.stop_slug, "dest": dest, "nights": nights, "days": [], "cut_total": 0}
            groups.append(current)
        if day.cut:
            current["cut_total"] += 1
            if current["cut_total"] > CUT_ROWS_SHOWN:
                continue
        current["days"].append(day)
    for group in groups:
        group["cut_more"] = max(0, group["cut_total"] - CUT_ROWS_SHOWN)
    departure = it.days[-1] if it.days else None
    near = plan["near"]
    base = _q(state)
    dests = {d.slug: d for d in plan["all_dests"]}
    hidden = {s for s, _ in state.stops} | {d.slug for d in journey_chips(plan)}
    return {
        "popular": [{"dest": dests[s], "href": base + f"&add={s}"} for s in POPULAR if s in dests and s not in hidden],
        "request": request,
        "plan": plan, "state": state, "itinerary": it, "stops": stops, "day_groups": groups,
        "departure": departure,
        "near": near,
        "near_add": (base + f"&add={near[0].slug}") if near else "",
        "budget": b,
        "money": {k: money(getattr(b, k), currency) for k in
                  ("flights", "lodging", "meals", "transport", "extras", "total", "per_person")} if b else {},
        "tier_label": TIER_LABELS.get(state.tier, "Mid-range"),
        "max_stops": plan["max_stops"],
        "max_stops_word": NUMBER_WORDS.get(plan["max_stops"], plan["max_stops"]).lower(),
    }


def render_fragments(request, plan):
    ctx = fragment_context(request, plan)
    return {name: render_to_string(template, ctx, request=request) for name, template in FRAGMENTS.items()}


def build_with_fragments(request):
    """/plan/build/ payload: the JSON data plus the rendered fragments.
    No per-user preselect, so the answer is the same for everyone and can be
    cached."""
    plan = build_plan(request, request.GET)
    data = plan_json(plan)
    data["html"] = render_fragments(request, plan)
    return data


def page_context(request, page):
    plan = build_plan(request, request.GET, user=request.user)
    ctx = fragment_context(request, plan)
    state = plan["state"]
    base = _q(state)
    query = state.query()
    q = (request.GET.get("q") or "").strip()
    links_allowed = booking_links_allowed(request)
    ctx.update({
        "page": page,
        "query": query,
        "share_path": page.url + "?" + query,
        "share_url": request.build_absolute_uri(page.url + "?" + query),
        "journey": [{"dest": d, "href": base + f"&add={d.slug}"} for d in journey_chips(plan)],
        "search_q": q,
        "search_results": [dict(r, href=(base + f"&add={r['dest']}") if r["dest"] else "")
                           for r in run_search(q)] if q else [],
        "added_from": plan["added_from"],
        "unplannable": plan["unplannable"],
        "messages": plan["messages"],
        "party_options": range(1, PARTY_MAX + 1),
        "pace_options": PACE_CHOICES,
        "tier_options": list(TIER_LABELS.items()),
        "booking_links": list(PlannerBookingLink.objects.filter(active=True)) if links_allowed else [],
        "disclosure_url": affiliate_disclosure_url(request) if links_allowed else "",
        "first_stop": plan["stops"][0][0] if plan["stops"] else None,
        "login_url": reverse("account_login") + "?next=" + quote(page.url + "?" + query, safe=""),
        "group_tours": _route_tours(request, plan),
    })
    return ctx


def _route_tours(request, plan):
    """Live guided pilgrimages that visit any site on the route (only when
    the v2 tours are switched on for this request); else [] and the card
    shows the None state."""
    from core.v2 import v2_enabled

    if not plan["stops"] or not v2_enabled(request):
        return []
    from tours.models import GuidedPilgrimage

    site_pks = {s.pk for dest, _ in plan["stops"] for s in dest.sites}
    site_pks |= {s.pk for dest, _ in plan["stops"] for d in dest.curated for s in d.sites}
    if not site_pks:
        return []
    tours = (GuidedPilgrimage.objects.public().filter(stops__site__in=site_pks).distinct()
             .select_related("operator"))
    # Never sample tours (manage.py v2_dev_sample): the card falls back to the None state.
    return [t for t in tours if not t.is_sample][:3]
