from django import template

from core.v2 import planner_v2_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def planner_trips_url(context):
    """{% planner_trips_url as trips_url %}: My Trips (/plan/trips/) for a
    signed-in pilgrim while SOG_PLANNER_V2 allows the request, else "".
    One query per request however many menus ask."""
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or not getattr(user, "is_authenticated", False) or not planner_v2_enabled(request):
        return ""
    if not hasattr(request, "_planner_trips_url"):
        from planner.models import PlanPage

        page = PlanPage.objects.live().first()
        request._planner_trips_url = (page.get_url(request) + "trips/") if page else ""
    return request._planner_trips_url


@register.filter
def date_range(start, end):
    """"May 10–17, 2027", "May 30 – Jun 2, 2027", "Dec 28, 2027 – Jan 3, 2028"."""
    if not start:
        return ""
    if not end or end == start:
        return f"{start:%b} {start.day}, {start.year}"
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"
    return f"{start:%b} {start.day}–{end.day}, {end.year}"
