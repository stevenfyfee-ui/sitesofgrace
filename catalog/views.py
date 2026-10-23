from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from wagtail.models import Page

from catalog.models import LodgingClickDaily, PilgrimageTrailPage, SacredSitePage, SiteLodging
from core.v2 import v2_enabled
from pilgrims.models import SiteVisit


@require_GET
def go_lodging(request, pk):
    """/go/lodging/<id>/?from=<page id>: count the "Check availability" click,
    then 302 to the booking link (or the website). v2 only; same privacy as
    /go/tour/: only (lodging, page, date, count) is stored -- no IP, user or
    cookie."""
    if not v2_enabled(request):
        raise Http404
    lodging = get_object_or_404(SiteLodging.objects.select_related("page"), pk=pk)
    if not lodging.page.live or not lodging.outbound_url:
        raise Http404
    page = None
    source = request.GET.get("from", "")
    if source.isdigit():
        page = Page.objects.filter(pk=int(source)).first()
    LodgingClickDaily.record(lodging, page)
    response = HttpResponseRedirect(lodging.outbound_url)
    response["Cache-Control"] = "no-store"
    return response


def sites_json(request):
    sites = SacredSitePage.objects.live().exclude(latitude=None).exclude(longitude=None)

    journey_statuses = {}
    if request.user.is_authenticated:
        journey_statuses = dict(
            SiteVisit.objects.filter(owner=request.user, site__in=sites).values_list(
                "site_id", "status"
            )
        )

    return JsonResponse({
        "sites": [
            {
                "id": site.pk,
                "slug": site.slug,
                "title": site.title,
                "category": site.category,
                "locality": site.locality,
                "country": site.country,
                "latitude": float(site.latitude),
                "longitude": float(site.longitude),
                "url": site.url,
                "summary_short": site.summary_short,
                "journey_status": journey_statuses.get(site.pk),
            }
            for site in sites
        ]
    })


def trails_json(request):
    """The trail lines for the interactive map.

    Deliberately a second endpoint rather than another key on
    sacred-sites.json: the pins are per-visitor (they carry the signed-in
    pilgrim's journey status) while the lines are the same for everybody, so
    keeping them apart lets this one be cached later without touching the
    other. `?trail=<slug>` narrows it to one route, which is what a trail
    page's own map asks for.
    """
    trails = PilgrimageTrailPage.objects.live().prefetch_related("stops__site")

    slug = request.GET.get("trail")
    if slug:
        trails = trails.filter(slug=slug)

    payloads = [trail.map_payload() for trail in trails]
    # A one-stop trail has no line to draw; sending it anyway would put a
    # lone unnumbered marker on the map with nothing to explain it.
    return JsonResponse({"trails": [p for p in payloads if len(p["stops"]) >= 2]})
