from django.http import JsonResponse

from catalog.models import SacredSitePage
from community.models import JourneyEntry


def sites_json(request):
    sites = SacredSitePage.objects.live().exclude(latitude=None).exclude(longitude=None)

    journey_statuses = {}
    if request.user.is_authenticated:
        journey_statuses = dict(
            JourneyEntry.objects.filter(user=request.user, site__in=sites).values_list(
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
