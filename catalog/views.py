from django.http import JsonResponse

from catalog.models import PilgrimageTrailPage, SacredSitePage
from pilgrims.models import SiteVisit


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
