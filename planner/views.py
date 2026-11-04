"""Outbound booking links from the Trip Planner v2 sidebar."""
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from core.v2 import planner_v2_enabled

from .booking import booking_links_allowed
from .models import DestinationCost, PlannerBookingClickDaily, PlannerBookingLink


@require_GET
def go_planner(request, pk):
    """/go/planner/<link id>/?dest=<first stop slug>: count the click, then
    302 to the link's URL with {dest_slug}, {sub_id} and {iata} filled in.

    404 unless SOG_PLANNER_V2 allows the request AND booking links are
    allowed right now (Settings > Trip planner on, Affiliate Disclosure
    live; checked on every click, not only when the setting was saved).
    Records only (link, destination, date, count). Nothing about the visitor
    is read or stored, and the response sets no cookie."""
    if not planner_v2_enabled(request) or not booking_links_allowed(request):
        raise Http404
    link = get_object_or_404(PlannerBookingLink, pk=pk, active=True)
    dest = get_object_or_404(DestinationCost, slug=(request.GET.get("dest") or "").strip())
    PlannerBookingClickDaily.record(link, dest)
    response = HttpResponseRedirect(link.fill(dest.slug, dest.gateway_airport_iata or dest.nearest_airport_iata))
    response["Cache-Control"] = "no-store"
    return response
