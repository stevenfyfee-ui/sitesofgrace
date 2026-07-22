from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.models import SacredSitePage

from .forms import PilgrimProfileForm
from .models import JourneyEntry, PilgrimProfile

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


@login_required
def passport_dashboard(request):
    profile, _ = PilgrimProfile.objects.get_or_create(user=request.user)
    entries = list(
        JourneyEntry.objects.filter(user=request.user)
        .select_related("site")
        .order_by("site__title")
    )
    has_map_sites = any(
        entry.site.latitude is not None and entry.site.longitude is not None for entry in entries
    )

    context = {
        "profile": profile,
        "has_map_sites": has_map_sites,
        "initial": (profile.display_name or request.user.get_username())[:1].upper(),
        "visited_entries": [e for e in entries if e.status == JourneyEntry.STATUS_VISITED],
        "want_entries": [e for e in entries if e.status == JourneyEntry.STATUS_WANT],
        "saved_entries": [e for e in entries if e.status == JourneyEntry.STATUS_SAVED],
    }
    return render(request, "community/passport.html", context)


@login_required
def passport_journey_json(request):
    entries = (
        JourneyEntry.objects.filter(
            user=request.user,
            site__live=True,
            site__latitude__isnull=False,
            site__longitude__isnull=False,
        )
        .select_related("site")
    )
    return JsonResponse({
        "sites": [
            {
                "name": entry.site.title,
                "url": entry.site.url,
                "lat": float(entry.site.latitude),
                "lng": float(entry.site.longitude),
                "status": entry.status,
            }
            for entry in entries
        ]
    })


@login_required
def passport_profile_edit(request):
    profile, _ = PilgrimProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = PilgrimProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("passport")
    else:
        form = PilgrimProfileForm(instance=profile)
    return render(request, "community/profile_edit.html", {"form": form, "profile": profile})
