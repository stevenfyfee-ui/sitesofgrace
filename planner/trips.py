"""Saved trips (Trip Planner v2, phase 4): save, My Trips, rename, delete,
share on/off, and the read-only shared view.

All of these are PlanPage routes (planner/models.py), so they 404 unless
SOG_PLANNER_V2 allows the request. Every write is a CSRF-checked POST, and
every trip is looked up with owner=request.user, so another account (staff
included) gets a 404, never someone else's trip. Writes are rate-limited the
way the pilgrim endpoints are: count the user's own recent writes, answer
{"error": "rate_limited"}. No IP is involved.

A Trip stores only the plan's inputs; the itinerary and budget are rebuilt
from current data every time one is shown.
"""
import secrets
from datetime import timedelta

from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.utils import timezone

from planner.itinerary import build_itinerary, money
from planner.models import DestinationCost, PlannerSettings, Trip, TripStop
from planner.page import absolute_url
from planner.plan_data import load_destinations, load_pricing
from planner.urlstate import PlanState, parse_state

TRIP_WRITES_PER_HOUR = 30
MAX_TRIPS_PER_USER = 50
TITLE_MAX = Trip._meta.get_field("title").max_length


def wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def answer(request, ok, error="", message="", redirect="", **data):
    """JSON for plan-v2.js, a redirect for a plain form post."""
    if wants_json(request):
        return JsonResponse({"success": ok, "error": error, "message": message, **data}, status=200)
    return HttpResponseRedirect(redirect)


def require_owner_post(request):
    if request.method != "POST":
        raise Http404
    if not request.user.is_authenticated:
        raise Http404


def rate_limited(user):
    since = timezone.now() - timedelta(hours=1)
    return Trip.objects.filter(owner=user, updated__gte=since).count() >= TRIP_WRITES_PER_HOUR


def trip_state(trip):
    return PlanState(stops=[(s.destination.slug, s.nights) for s in trip.stops.select_related("destination")],
                     start_date=trip.start_date, party=trip.party, tier=trip.tier, pace=trip.pace)


def default_title(stops):
    names = [d.short_name for d, _ in stops] or ["My pilgrimage"]
    title = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]
    return title[:TITLE_MAX]


def summarize(trips, request=None):
    """Each trip with its route and a freshly calculated total."""
    pricing = load_pricing(request)
    out = []
    for trip in trips:
        state = trip_state(trip)
        data = load_destinations([s for s, _ in state.stops], request)
        stops = [(data[s], n) for s, n in state.stops if s in data]
        it = build_itinerary(stops, state.start_date, state.party, state.tier, state.pace, pricing=pricing)
        out.append({
            "trip": trip, "state": state, "stops": stops, "itinerary": it,
            "total": money(it.budget.total, pricing.currency) if it.budget else "",
            "query": state.query() + f"&trip={trip.pk}",
        })
    return out


# --- views -----------------------------------------------------------------

def my_trips(request, page):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    trips = summarize(Trip.objects.filter(owner=request.user), request)
    return TemplateResponse(request, "planner/v2/my_trips.html", {
        "page": page, "self": page, "trips": trips,
        "flash": request.GET.get("done", ""),
        "share_base": absolute_url(page, request, "t/"),
    })


def save(request, page):
    """Create a trip from the posted plan (q=<plan query>), or update the
    pilgrim's own trip when trip=<id> is posted."""
    require_owner_post(request)
    plan_url = page.url
    raw = request.POST.get("q", "")
    max_stops = PlannerSettings.load(request_or_site=request).max_stops
    state = parse_state(QueryDict(raw), set(DestinationCost.objects.values_list("slug", flat=True)), max_stops)
    back = plan_url + "?" + state.query()
    if not state.stops:
        return answer(request, False, "invalid", "Add a place before saving.", back)
    if rate_limited(request.user):
        return answer(request, False, "rate_limited", "You've saved a lot this hour. Try again later.", back)

    trip_id = request.POST.get("trip", "")
    trip = None
    if trip_id:
        if not trip_id.isdigit():
            raise Http404
        trip = get_object_or_404(Trip, pk=int(trip_id), owner=request.user)
    elif Trip.objects.filter(owner=request.user).count() >= MAX_TRIPS_PER_USER:
        return answer(request, False, "too_many", f"You can keep up to {MAX_TRIPS_PER_USER} trips. "
                                                  "Delete one in My Trips first.", back)

    data = load_destinations([s for s, _ in state.stops], request)
    stops = [(data[s], n) for s, n in state.stops if s in data]
    dests = {d.slug: d for d in DestinationCost.objects.filter(slug__in=[s for s, _ in state.stops])}
    with transaction.atomic():
        if trip is None:
            trip = Trip(owner=request.user, title=default_title(stops))
        trip.start_date, trip.party, trip.tier, trip.pace = state.start_date, state.party, state.tier, state.pace
        trip.save()
        trip.stops.all().delete()
        TripStop.objects.bulk_create([
            TripStop(trip=trip, destination=dests[slug], nights=n, sort_order=i)
            for i, (slug, n) in enumerate(state.stops)
        ])
    return answer(request, True, message="Saved to My Pilgrimage › My Trips.",
                  redirect=back + f"&trip={trip.pk}&saved=1", trip=trip.pk, title=trip.title,
                  my_trips_url=page.url + "trips/")


def _owned(request, trip_id):
    require_owner_post(request)
    return get_object_or_404(Trip, pk=trip_id, owner=request.user)


def rename(request, page, trip_id):
    trip = _owned(request, trip_id)
    back = page.url + "trips/"
    if rate_limited(request.user):
        return answer(request, False, "rate_limited", "Too many changes this hour. Try again later.", back)
    title = " ".join((request.POST.get("title") or "").split())[:TITLE_MAX]
    if not title:
        return answer(request, False, "invalid", "Give the trip a name.", back)
    trip.title = title
    trip.save(update_fields=["title", "updated"])
    return answer(request, True, message="Renamed.", redirect=back + "?done=renamed", title=title)


def delete(request, page, trip_id):
    trip = _owned(request, trip_id)
    trip.delete()
    return answer(request, True, message="Trip deleted.", redirect=page.url + "trips/?done=deleted")


def share(request, page, trip_id):
    """on=1: a new unguessable token (a fresh one each time sharing is turned
    on, so an old link never comes back to life). Anything else: off."""
    trip = _owned(request, trip_id)
    back = page.url + "trips/"
    if rate_limited(request.user):
        return answer(request, False, "rate_limited", "Too many changes this hour. Try again later.", back)
    if request.POST.get("on") == "1":
        trip.share_token = secrets.token_urlsafe(16)
        done = "shared"
    else:
        trip.share_token = None
        done = "unshared"
    trip.save(update_fields=["share_token", "updated"])
    url = absolute_url(page, request, f"t/{trip.share_token}/") if trip.share_token else ""
    return answer(request, True, redirect=back + f"?done={done}", share_url=url)


def shared(request, page, token):
    """Read-only view of a shared trip. Nothing about the owner is shown,
    search engines are told not to index it, and the token isn't sent on in
    the Referer header."""
    trip = Trip.objects.filter(share_token=token).first() if token else None
    if trip is None:
        raise Http404
    summary = summarize([trip], request)[0]
    from planner.page import fragment_context
    from planner.api import build_plan

    plan = build_plan(request, QueryDict(summary["state"].query()))
    ctx = fragment_context(request, plan)
    ctx.update({
        "page": page, "self": page, "trip": trip,
        "open_url": page.url + "?" + summary["state"].query(),
        "hide_cut": True,
        "route_eyebrow": "This pilgrimage",
    })
    response = TemplateResponse(request, "planner/v2/shared.html", ctx)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "same-origin"
    response["Cache-Control"] = "private, no-store"
    return response
