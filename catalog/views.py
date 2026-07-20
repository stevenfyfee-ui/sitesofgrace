from django.http import JsonResponse

from catalog.models import SacredSitePage


def sites_json(request):
    sites = SacredSitePage.objects.live().exclude(latitude=None).exclude(longitude=None)
    return JsonResponse({
        "sites": [
            {
                "slug": site.slug,
                "title": site.title,
                "category": site.category,
                "locality": site.locality,
                "country": site.country,
                "latitude": float(site.latitude),
                "longitude": float(site.longitude),
                "url": site.url,
            }
            for site in sites
        ]
    })
