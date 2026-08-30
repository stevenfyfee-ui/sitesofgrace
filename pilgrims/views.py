from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalog.models import SacredSitePage

from . import imaging
from .forms import ProfileSettingsForm
from .models import Block, Follow, PilgrimPhoto, PilgrimProfile, SiteVisit
from .permissions import can_interact, can_view_profile_detail, can_view_photo, is_following

User = get_user_model()

FOLLOW_REQUESTS_PER_DAY = 50
PHOTO_UPLOADS_PER_HOUR = 100


def _redirect_next(request, flag):
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    separator = "&" if "?" in next_url else "?"
    return HttpResponseRedirect(f"{next_url}{separator}{flag}=1")


# --- Core portal views ------------------------------------------------------

def portal_home(request):
    if request.user.is_authenticated:
        # No feed yet (phase 3) — the pilgrim's own profile is the interim
        # landing spot.
        return redirect("pilgrims:profile_detail", handle=request.user.pilgrim.handle)
    return render(request, "pilgrims/marketing.html")


def profile_detail(request, handle):
    profile = get_object_or_404(PilgrimProfile.objects.select_related("user"), handle=handle)
    owner = profile.user
    viewer = request.user

    can_view = can_view_profile_detail(viewer, owner)
    is_self = viewer.is_authenticated and viewer.pk == owner.pk
    viewer_blocked_owner = viewer.is_authenticated and Block.objects.filter(
        blocker=viewer, blocked=owner
    ).exists()
    owner_blocked_viewer = viewer.is_authenticated and Block.objects.filter(
        blocker=owner, blocked=viewer
    ).exists()
    is_blocked = viewer_blocked_owner or owner_blocked_viewer

    follow_state = None
    if viewer.is_authenticated and not is_self and not is_blocked:
        existing = Follow.objects.filter(follower=viewer, following=owner).first()
        follow_state = existing.status if existing else None

    context = {
        "profile": profile,
        "owner": owner,
        "can_view": can_view,
        "is_self": is_self,
        "is_blocked": is_blocked,
        "viewer_blocked_owner": viewer_blocked_owner,
        "owner_blocked_viewer": owner_blocked_viewer,
        "follow_state": follow_state,
        "follower_count": Follow.objects.filter(following=owner, status=Follow.STATUS_ACCEPTED).count(),
        "following_count": Follow.objects.filter(follower=owner, status=Follow.STATUS_ACCEPTED).count(),
        "pending_request_count": Follow.objects.filter(
            following=owner, status=Follow.STATUS_PENDING
        ).count() if is_self else 0,
        "badges": owner.awarded_badges.select_related("badge").order_by("badge__sort_order"),
    }

    if can_view:
        visits = SiteVisit.objects.filter(owner=owner).select_related("site")
        context["visited"] = [v for v in visits if v.status == SiteVisit.STATUS_VISITED]
        context["want_to_go"] = [v for v in visits if v.status == SiteVisit.STATUS_WANT_TO_GO]
        context["has_map_sites"] = any(
            v.site.latitude is not None and v.site.longitude is not None for v in visits
        )

    return render(request, "pilgrims/profile_detail.html", context)


@login_required
def profile_settings(request):
    profile = request.user.pilgrim
    if request.method == "POST":
        form = ProfileSettingsForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('pilgrims:settings')}?saved=1")
    else:
        form = ProfileSettingsForm(instance=profile)
    return render(request, "pilgrims/settings.html", {"form": form, "profile": profile})


@login_required
def follow_requests(request):
    incoming = Follow.objects.filter(
        following=request.user, status=Follow.STATUS_PENDING
    ).select_related("follower", "follower__pilgrim").order_by("-created_at")
    return render(request, "pilgrims/requests.html", {"incoming": incoming})


@login_required
def following_list(request):
    rows = Follow.objects.filter(
        follower=request.user, status=Follow.STATUS_ACCEPTED
    ).select_related("following", "following__pilgrim").order_by("-created_at")
    return render(request, "pilgrims/following.html", {"rows": rows})


@login_required
def followers_list(request):
    rows = Follow.objects.filter(
        following=request.user, status=Follow.STATUS_ACCEPTED
    ).select_related("follower", "follower__pilgrim").order_by("-created_at")
    return render(request, "pilgrims/followers.html", {"rows": rows})


# --- POST actions ------------------------------------------------------------

@login_required
@require_POST
def follow_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        return _redirect_next(request, "follow_error")
    if not can_interact(request.user, target):
        return _redirect_next(request, "blocked_error")

    since = timezone.now() - timedelta(hours=24)
    sent_today = Follow.objects.filter(follower=request.user, created_at__gte=since).count()
    if sent_today >= FOLLOW_REQUESTS_PER_DAY:
        return _redirect_next(request, "rate_limited")

    existing = Follow.objects.filter(follower=request.user, following=target).first()
    if existing:
        return _redirect_next(request, "already_following")

    is_private = getattr(target.pilgrim, "is_private", True)
    status = Follow.STATUS_PENDING if is_private else Follow.STATUS_ACCEPTED
    Follow.objects.create(
        follower=request.user,
        following=target,
        status=status,
        responded_at=None if status == Follow.STATUS_PENDING else timezone.now(),
    )
    return _redirect_next(request, "requested" if status == Follow.STATUS_PENDING else "followed")


@login_required
@require_POST
def unfollow_user(request, user_id):
    Follow.objects.filter(follower=request.user, following_id=user_id).delete()
    return _redirect_next(request, "unfollowed")


@login_required
@require_POST
def approve_request(request, follow_id):
    follow = get_object_or_404(Follow, pk=follow_id, following=request.user, status=Follow.STATUS_PENDING)
    follow.status = Follow.STATUS_ACCEPTED
    follow.responded_at = timezone.now()
    follow.save(update_fields=["status", "responded_at"])
    return _redirect_next(request, "approved")


@login_required
@require_POST
def decline_request(request, follow_id):
    follow = get_object_or_404(Follow, pk=follow_id, following=request.user, status=Follow.STATUS_PENDING)
    follow.delete()
    return _redirect_next(request, "declined")


@login_required
@require_POST
def remove_follower(request, user_id):
    Follow.objects.filter(follower_id=user_id, following=request.user).delete()
    return _redirect_next(request, "removed")


@login_required
@require_POST
def block_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        return _redirect_next(request, "block_error")

    Block.objects.get_or_create(blocker=request.user, blocked=target)
    # A block severs any existing follow relationship in either direction.
    Follow.objects.filter(follower=request.user, following=target).delete()
    Follow.objects.filter(follower=target, following=request.user).delete()
    return _redirect_next(request, "blocked")


@login_required
@require_POST
def unblock_user(request, user_id):
    Block.objects.filter(blocker=request.user, blocked_id=user_id).delete()
    return _redirect_next(request, "unblocked")


# --- Legacy /passport/ and /journey/ compatibility --------------------------
# Preserves the exact URL names the existing home page, catalog site pages,
# and interactive map already reference by name, so none of those templates
# needed to change when the `community` app was absorbed into `pilgrims`.

@login_required
def passport_dashboard(request):
    return redirect("pilgrims:profile_detail", handle=request.user.pilgrim.handle)


@login_required
def passport_profile_edit(request):
    return redirect("pilgrims:settings")


@login_required
def passport_journey_json(request):
    visits = SiteVisit.objects.filter(
        owner=request.user,
        site__live=True,
        site__latitude__isnull=False,
        site__longitude__isnull=False,
    ).select_related("site")
    return JsonResponse({
        "sites": [
            {
                "name": visit.site.title,
                "url": visit.site.url,
                "lat": float(visit.site.latitude),
                "lng": float(visit.site.longitude),
                "status": visit.status,
            }
            for visit in visits
        ]
    })


VALID_VISIT_STATUSES = {choice for choice, _ in SiteVisit.STATUS_CHOICES}


@require_POST
def site_visit_toggle(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    site_id = request.POST.get("site_id")
    status = request.POST.get("status")
    if not site_id or status not in VALID_VISIT_STATUSES:
        return JsonResponse({"detail": "Invalid request."}, status=400)

    site = get_object_or_404(SacredSitePage, pk=site_id)

    visit = SiteVisit.objects.filter(owner=request.user, site=site).first()
    if visit and visit.status == status:
        visit.delete()
        new_status = None
    else:
        defaults = {"status": status}
        if status == SiteVisit.STATUS_VISITED:
            defaults["visited_on"] = timezone.localdate()
        visit, _ = SiteVisit.objects.update_or_create(
            owner=request.user, site=site, defaults=defaults
        )
        new_status = visit.status

    return JsonResponse({"status": new_status})


# --- Photos (phase 2) --------------------------------------------------------

def _mark_visited(owner, site):
    """Same model, same manager pattern as site_visit_toggle above — the
    upload flow's "mark visited" checkbox is not a second way to create a
    visit, just another caller of it. Never overwrites an existing
    visited_on, and only upgrades (never downgrades) an existing status."""
    visit, created = SiteVisit.objects.get_or_create(
        owner=owner, site=site,
        defaults={"status": SiteVisit.STATUS_VISITED, "visited_on": timezone.localdate()},
    )
    if not created and visit.status != SiteVisit.STATUS_VISITED:
        visit.status = SiteVisit.STATUS_VISITED
        if not visit.visited_on:
            visit.visited_on = timezone.localdate()
        visit.save(update_fields=["status", "visited_on"])
    return visit


def _photo_thumb_context(photo):
    return {
        "uuid": str(photo.uuid),
        "caption": photo.caption,
        "thumb_url": photo.thumb.url,
    }


@login_required
def photo_site_search(request):
    """Backs the searchable site picker on the upload form."""
    query = request.GET.get("q", "").strip()
    sites = SacredSitePage.objects.live()
    if query:
        sites = sites.filter(title__icontains=query)
    sites = sites.order_by("title")[:20]
    return JsonResponse({
        "sites": [
            {
                "id": site.pk,
                "slug": site.slug,
                "title": site.title,
                "locality": site.locality,
                "country": site.country,
                "already_visited": SiteVisit.objects.filter(
                    owner=request.user, site=site, status=SiteVisit.STATUS_VISITED
                ).exists(),
            }
            for site in sites
        ]
    })


@login_required
def photo_upload(request):
    if request.method != "POST":
        return render(request, "pilgrims/photo_upload.html")

    since = timezone.now() - timedelta(hours=1)
    uploaded_this_hour = PilgrimPhoto.objects.filter(
        owner=request.user, created_at__gte=since
    ).count()
    if uploaded_this_hour >= PHOTO_UPLOADS_PER_HOUR:
        return JsonResponse(
            {"success": False, "error": "rate_limited",
             "message": "You've uploaded a lot of photos this hour — try again later."},
            status=200,
        )

    site_id = request.POST.get("site_id")
    upload = request.FILES.get("photo")
    if not site_id or not upload:
        return JsonResponse(
            {"success": False, "error": "invalid", "message": "Missing site or file."}, status=200
        )
    site = get_object_or_404(SacredSitePage.objects.live(), pk=site_id)

    try:
        processed = imaging.process_upload(upload)
    except imaging.UploadTooLargeError as exc:
        return JsonResponse({"success": False, "error": "too_large", "message": str(exc)}, status=200)
    except imaging.UnsupportedImageError as exc:
        return JsonResponse({"success": False, "error": "unsupported", "message": str(exc)}, status=200)

    if PilgrimPhoto.objects.filter(owner=request.user, content_hash=processed.content_hash).exists():
        return JsonResponse(
            {"success": False, "error": "duplicate",
             "message": "You've already uploaded this photo."},
            status=200,
        )

    caption = request.POST.get("caption", "")[:300]
    taken_on = request.POST.get("taken_on") or None
    photo = PilgrimPhoto.create_from_processed(
        owner=request.user, site=site, processed=processed, caption=caption, taken_on=taken_on,
    )

    if request.POST.get("mark_visited") == "on":
        _mark_visited(request.user, site)

    return JsonResponse({"success": True, "photo": _photo_thumb_context(photo)})


@login_required
def photo_library(request):
    """Grouped by site, most-recently-active site first."""
    site_ids = list(
        PilgrimPhoto.objects.filter(owner=request.user)
        .values("site_id")
        .annotate(last_activity=Max("created_at"))
        .order_by("-last_activity")
        .values_list("site_id", flat=True)
    )
    sites_by_id = SacredSitePage.objects.in_bulk(site_ids)
    visited_site_ids = set(
        SiteVisit.objects.filter(
            owner=request.user, site_id__in=site_ids, status=SiteVisit.STATUS_VISITED
        ).values_list("site_id", flat=True)
    )

    groups = []
    for site_id in site_ids:
        site = sites_by_id.get(site_id)
        if site is None:
            continue
        photos = list(PilgrimPhoto.objects.filter(owner=request.user, site=site)[:6])
        groups.append({
            "site": site,
            "count": PilgrimPhoto.objects.filter(owner=request.user, site=site).count(),
            "preview_photos": photos,
            "is_visited": site_id in visited_site_ids,
        })

    return render(request, "pilgrims/photo_library.html", {"groups": groups})


@login_required
def photo_album(request, site_slug):
    site = get_object_or_404(SacredSitePage, slug=site_slug)
    photos = PilgrimPhoto.objects.filter(owner=request.user, site=site)
    is_visited = SiteVisit.objects.filter(
        owner=request.user, site=site, status=SiteVisit.STATUS_VISITED
    ).exists()
    return render(request, "pilgrims/photo_album.html", {
        "site": site, "photos": photos, "is_visited": is_visited,
    })


@login_required
def photo_detail(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto.objects.select_related("site", "owner"), uuid=photo_uuid)
    if not can_view_photo(request.user, photo):
        raise Http404
    return render(request, "pilgrims/photo_detail.html", {"photo": photo})


@login_required
@require_POST
def photo_delete(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid, owner=request.user)
    site_slug = photo.site.slug
    photo.delete()
    return HttpResponseRedirect(f"{reverse('pilgrims:photo_album', args=[site_slug])}?deleted=1")


@login_required
@require_POST
def photo_bulk_delete(request):
    photo_uuids = request.POST.getlist("photo_uuid")
    qs = PilgrimPhoto.objects.filter(owner=request.user, uuid__in=photo_uuids)
    site = qs.first().site if qs.exists() else None
    count = qs.count()
    qs.delete()
    if site is None:
        return redirect("pilgrims:photo_library")
    return HttpResponseRedirect(
        f"{reverse('pilgrims:photo_album', args=[site.slug])}?deleted={count}"
    )


@login_required
@require_POST
def photo_caption_edit(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid, owner=request.user)
    photo.caption = request.POST.get("caption", "")[:300]
    photo.save(update_fields=["caption", "updated_at"])
    return JsonResponse({"success": True, "caption": photo.caption})
