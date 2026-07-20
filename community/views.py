from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from catalog.models import SacredSitePage

from .models import JourneyEntry

VALID_STATUSES = {choice for choice, _ in JourneyEntry.STATUS_CHOICES}


@require_POST
def set_journey_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    site_id = request.POST.get("site_id")
    status = request.POST.get("status")
    if not site_id or status not in VALID_STATUSES:
        return JsonResponse({"detail": "Invalid request."}, status=400)

    site = get_object_or_404(SacredSitePage, pk=site_id)

    entry = JourneyEntry.objects.filter(user=request.user, site=site).first()
    if entry and entry.status == status:
        entry.delete()
        new_status = None
    else:
        entry, _ = JourneyEntry.objects.update_or_create(
            user=request.user, site=site, defaults={"status": status}
        )
        new_status = entry.status

    return JsonResponse({"status": new_status})
