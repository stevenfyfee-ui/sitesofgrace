import base64
import hashlib
import logging
import uuid as uuid_module
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Max, Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from catalog.models import SacredSitePage

from . import imaging, sharing
from .forms import ProfileSettingsForm
from .models import (
    Block, Comment, Follow, Notification, PhotoReport, PilgrimPhoto, PilgrimProfile, Post,
    PostPhoto, SiteVisit,
)
from .moderation import apply_auto_hide_policy
from .permissions import (
    can_comment, can_interact, can_share_photo, can_view_photo, can_view_post,
    can_view_profile_detail, is_following, visible_posts_for,
)

User = get_user_model()

FOLLOW_REQUESTS_PER_DAY = 50
PHOTO_UPLOADS_PER_HOUR = 100
POSTS_PER_HOUR = 20
COMMENTS_PER_HOUR = 30
FEED_PAGE_SIZE = 20
PUBLIC_SHARES_PER_DAY = 10
REPORTS_PER_HOUR_PER_IP = 10


def _client_ip(request):
    """The real client IP — trusting exactly settings.TRUSTED_PROXY_COUNT
    hops of X-Forwarded-For, counted from the RIGHT, never the left.

    X-Forwarded-For is a client-suppliable header that each proxy hop
    APPENDS to (never replaces) as it forwards the request. A client that
    sends `X-Forwarded-For: 1.2.3.4` gets that value echoed straight back
    as the leftmost entry once App Platform's edge proxy appends the real
    address after it — `split(",")[0]` would trust the attacker completely.
    The trustworthy entries are the last TRUSTED_PROXY_COUNT of them, added
    by infrastructure we actually control.
    """
    trusted_count = settings.TRUSTED_PROXY_COUNT
    if trusted_count > 0:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
            if len(hops) >= trusted_count:
                return hops[-trusted_count]
    return request.META.get("REMOTE_ADDR", "")


def _ip_hash(request):
    ip = _client_ip(request)
    return hashlib.sha256(f"{ip}{settings.SECRET_KEY}".encode()).hexdigest()


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
        return redirect("pilgrims:feed")
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
    if status == Follow.STATUS_PENDING:
        Notification.objects.create(
            recipient=target, actor=request.user,
            verb=Notification.VERB_FOLLOW_REQUEST, target_uuid=request.user.pilgrim.uuid,
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
    Notification.objects.create(
        recipient=follow.follower, actor=request.user,
        verb=Notification.VERB_FOLLOW_ACCEPTED, target_uuid=request.user.pilgrim.uuid,
    )
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
        # A slug, not a pk: it's the id a pilgrim actually sees in a link
        # they might share or bookmark, and it doesn't leak an internal row
        # number the way a pk would. Anything that doesn't resolve to a
        # live site -- unknown slug, malformed value, draft page -- just
        # falls back to the normal empty picker; .filter().first() never
        # raises, so there's no 404/500 path to guard against here.
        site_slug = (request.GET.get("site") or "").strip()
        preselected_site = None
        preselected_already_visited = False
        if site_slug:
            preselected_site = SacredSitePage.objects.live().filter(slug=site_slug).first()
            if preselected_site:
                preselected_already_visited = SiteVisit.objects.filter(
                    owner=request.user, site=preselected_site, status=SiteVisit.STATUS_VISITED
                ).exists()
        return render(request, "pilgrims/photo_upload.html", {
            "preselected_site": preselected_site,
            "preselected_already_visited": preselected_already_visited,
        })

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

    # A shortcut through the UI, not through the rules: this is exactly the
    # same permission check, rate limit, and sharing.py call the standalone
    # pilgrims:photo_share view uses -- no second code path, no bypass of
    # the private-to-public copy.
    shared = False
    share_error = None
    if request.POST.get("share_publicly") == "on":
        if not can_share_photo(request.user, photo):
            share_error = "You can't share photos publicly right now."
        else:
            since_share = timezone.now() - timedelta(hours=24)
            shared_today = PilgrimPhoto.objects.filter(
                owner=request.user, public_shared_at__gte=since_share
            ).count()
            if shared_today >= PUBLIC_SHARES_PER_DAY:
                share_error = "You've shared a lot today — try again tomorrow."
            else:
                sharing.share_photo(photo, credit=request.user.pilgrim.public_credit_default)
                shared = True

    return JsonResponse({
        "success": True,
        "photo": _photo_thumb_context(photo),
        "shared": shared,
        "share_error": share_error,
    })


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
    return render(request, "pilgrims/photo_detail.html", {
        "photo": photo,
        "can_share": can_share_photo(request.user, photo),
        "credit_choices": PilgrimProfile.CREDIT_CHOICES,
    })


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


# --- Feed, posts, comments (phase 3) -----------------------------------------

def _encode_cursor(post):
    raw = f"{post.created_at.isoformat()}|{post.uuid}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(raw):
    try:
        decoded = base64.urlsafe_b64decode(raw.encode()).decode()
        created_at_str, uuid_str = decoded.split("|", 1)
        created_at = timezone.datetime.fromisoformat(created_at_str)
        return created_at, uuid_module.UUID(uuid_str)
    except (ValueError, TypeError):
        return None


@login_required
def feed(request):
    qs = visible_posts_for(request.user)

    cursor = request.GET.get("cursor")
    decoded = _decode_cursor(cursor) if cursor else None
    if decoded:
        cursor_created_at, cursor_uuid = decoded
        qs = qs.filter(
            Q(created_at__lt=cursor_created_at)
            | (Q(created_at=cursor_created_at) & Q(uuid__lt=cursor_uuid))
        )

    posts = list(qs.order_by("-created_at", "-uuid")[: FEED_PAGE_SIZE + 1])
    has_more = len(posts) > FEED_PAGE_SIZE
    posts = posts[:FEED_PAGE_SIZE]
    next_cursor = _encode_cursor(posts[-1]) if posts and has_more else None

    follows_nobody = not decoded and not accepted_following_ids_exists(request.user)

    return render(request, "pilgrims/feed.html", {
        "posts": posts,
        "next_cursor": next_cursor,
        "is_first_page": cursor is None,
        "follows_nobody": follows_nobody,
    })


def accepted_following_ids_exists(user):
    return Follow.objects.filter(follower=user, status=Follow.STATUS_ACCEPTED).exists()


@login_required
def compose_photos_for_site(request):
    site_id = request.GET.get("site_id")
    photos = PilgrimPhoto.objects.filter(owner=request.user, site_id=site_id).order_by("-created_at")
    return JsonResponse({
        "photos": [
            {"uuid": str(p.uuid), "thumb_url": p.thumb.url, "caption": p.caption}
            for p in photos
        ]
    })


@login_required
def post_compose(request):
    if request.method != "POST":
        my_sites = (
            SacredSitePage.objects.filter(pilgrim_photos__owner=request.user)
            .distinct()
            .order_by("title")
        )
        return render(request, "pilgrims/post_compose.html", {"my_sites": my_sites})

    since = timezone.now() - timedelta(hours=1)
    posted_this_hour = Post.objects.filter(owner=request.user, created_at__gte=since).count()
    if posted_this_hour >= POSTS_PER_HOUR:
        return JsonResponse(
            {"success": False, "error": "rate_limited",
             "message": "You've posted a lot this hour — try again later."},
            status=200,
        )

    photo_uuids = request.POST.getlist("photo_uuid")
    caption = request.POST.get("caption", "")[:2000]
    if not photo_uuids:
        return JsonResponse(
            {"success": False, "error": "invalid", "message": "Choose at least one photo."},
            status=200,
        )

    photos = list(PilgrimPhoto.objects.filter(owner=request.user, uuid__in=photo_uuids))
    photos_by_uuid = {str(p.uuid): p for p in photos}
    ordered_photos = [photos_by_uuid[u] for u in photo_uuids if u in photos_by_uuid]
    if not ordered_photos:
        return JsonResponse(
            {"success": False, "error": "invalid", "message": "Those photos couldn't be found."},
            status=200,
        )

    sites = {p.site_id for p in ordered_photos}
    post_site_id = ordered_photos[0].site_id if len(sites) == 1 else None

    with transaction.atomic():
        post = Post.objects.create(
            owner=request.user, site_id=post_site_id, caption=caption,
            photo_count=len(ordered_photos),
        )
        PostPhoto.objects.bulk_create([
            PostPhoto(post=post, photo=photo, sort_order=i)
            for i, photo in enumerate(ordered_photos)
        ])

    return JsonResponse({"success": True, "post_uuid": str(post.uuid)})


@login_required
def post_detail(request, post_uuid):
    post = get_object_or_404(
        Post.objects.select_related("owner", "owner__pilgrim", "site"), uuid=post_uuid
    )
    if not can_view_post(request.user, post):
        raise Http404

    post_photos = list(post.post_photos.select_related("photo").order_by("sort_order"))
    comments = (
        Comment.objects.filter(post=post)
        .select_related("author", "author__pilgrim", "photo")
        .prefetch_related("replies__author", "replies__author__pilgrim")
        .order_by("created_at")
    )
    post_level_comments = [c for c in comments if c.photo_id is None and c.parent_id is None]
    comments_by_photo = {}
    for c in comments:
        if c.photo_id and c.parent_id is None:
            comments_by_photo.setdefault(c.photo_id, []).append(c)

    for pp in post_photos:
        pp.photo.thread = comments_by_photo.get(pp.photo_id, [])

    return render(request, "pilgrims/post_detail.html", {
        "post": post,
        "post_photos": post_photos,
        "post_level_comments": post_level_comments,
        "can_comment": can_comment(request.user, post),
    })


@login_required
@require_POST
def post_delete(request, post_uuid):
    post = get_object_or_404(Post, uuid=post_uuid, owner=request.user)
    post.delete()
    return redirect("pilgrims:feed")


@login_required
@require_POST
def comment_add(request, post_uuid):
    post = get_object_or_404(Post, uuid=post_uuid)
    if not can_comment(request.user, post):
        return JsonResponse(
            {"success": False, "error": "forbidden", "message": "You can't comment on this post."},
            status=200,
        )

    since = timezone.now() - timedelta(hours=1)
    posted_this_hour = Comment.objects.filter(author=request.user, created_at__gte=since).count()
    if posted_this_hour >= COMMENTS_PER_HOUR:
        return JsonResponse(
            {"success": False, "error": "rate_limited",
             "message": "You've commented a lot this hour — try again later."},
            status=200,
        )

    body = request.POST.get("body", "").strip()[:2000]
    if not body:
        return JsonResponse(
            {"success": False, "error": "invalid", "message": "Comment can't be empty."}, status=200
        )

    photo = None
    photo_uuid = request.POST.get("photo_uuid")
    if photo_uuid:
        photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid, post_photos__post=post)

    parent = None
    parent_uuid = request.POST.get("parent_uuid")
    if parent_uuid:
        parent = get_object_or_404(Comment, uuid=parent_uuid, post=post)
        if parent.parent_id:
            return JsonResponse(
                {"success": False, "error": "invalid",
                 "message": "Replies are one level deep only."},
                status=200,
            )

    comment = Comment(post=post, photo=photo, parent=parent, author=request.user, body=body)
    try:
        comment.full_clean()
    except ValidationError as exc:
        return JsonResponse(
            {"success": False, "error": "invalid", "message": " ".join(exc.messages)}, status=200
        )
    comment.save()
    Post.objects.filter(pk=post.pk).update(comment_count=F("comment_count") + 1)

    # Two independent facts, not one event: if the post owner is also the
    # parent comment's author, they get BOTH notifications — "someone
    # commented on your post" and "someone replied to your comment" are
    # both true and worth surfacing separately, not deduped into one.
    if post.owner_id != request.user.pk:
        Notification.objects.create(
            recipient=post.owner, actor=request.user,
            verb=Notification.VERB_COMMENT_ON_POST, target_uuid=post.uuid,
        )
    if parent and parent.author_id != request.user.pk:
        Notification.objects.create(
            recipient=parent.author, actor=request.user,
            verb=Notification.VERB_COMMENT_REPLY, target_uuid=post.uuid,
        )

    return JsonResponse({
        "success": True,
        "comment": {
            "uuid": str(comment.uuid),
            "body": comment.body,
            "author": comment.author.pilgrim.display_name or comment.author.pilgrim.handle,
        },
    })


@login_required
@require_POST
def comment_delete(request, comment_uuid):
    comment = get_object_or_404(Comment.objects.select_related("post"), uuid=comment_uuid)
    if request.user.pk not in (comment.author_id, comment.post.owner_id):
        raise Http404
    if not comment.is_deleted:
        comment.is_deleted = True
        comment.body = ""
        comment.save(update_fields=["is_deleted", "body"])
        Post.objects.filter(pk=comment.post_id).update(comment_count=F("comment_count") - 1)
    return JsonResponse({"success": True})


# --- Notifications (phase 3) -------------------------------------------------

@login_required
def notifications_list(request):
    notifications = list(
        Notification.objects.filter(recipient=request.user)
        .select_related("actor", "actor__pilgrim")
        .order_by("-created_at")[:50]
    )
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return render(request, "pilgrims/notifications.html", {"notifications": notifications})


# --- Public sharing (phase 4) -------------------------------------------------

@login_required
@require_POST
def photo_share(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid)
    if not can_share_photo(request.user, photo):
        return JsonResponse(
            {"success": False, "error": "forbidden", "message": "You can't share this photo publicly."},
            status=200,
        )

    since = timezone.now() - timedelta(hours=24)
    shared_today = PilgrimPhoto.objects.filter(owner=request.user, public_shared_at__gte=since).count()
    if shared_today >= PUBLIC_SHARES_PER_DAY:
        return JsonResponse(
            {"success": False, "error": "rate_limited",
             "message": "You've shared a lot today — try again tomorrow."},
            status=200,
        )

    credit = request.POST.get("credit", "")
    if credit not in dict(PilgrimProfile.CREDIT_CHOICES):
        credit = request.user.pilgrim.public_credit_default

    sharing.share_photo(photo, credit=credit)
    return JsonResponse({"success": True})


@login_required
@require_POST
def photo_unshare(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid, owner=request.user)
    sharing.unshare_photo(photo)
    return JsonResponse({"success": True})


def _send_moderation_email(report):
    from django.urls import reverse as url_reverse

    admin_path = url_reverse("pilgrim_moderation_photo_detail", args=[report.photo.uuid])
    admin_url = f"{settings.WAGTAILADMIN_BASE_URL}{admin_path}"
    try:
        send_mail(
            subject=f"[Sites of Grace] Photo reported: {report.get_reason_display()}",
            message=(
                f"A pilgrim photo was reported.\n\n"
                f"Reason: {report.get_reason_display()}\n"
                f"Note: {report.note or '(none)'}\n\n"
                f"Review it here: {admin_url}\n"
            ),
            from_email=None,
            recipient_list=[settings.MODERATION_EMAIL],
            fail_silently=False,
        )
    except Exception:
        logging.getLogger(__name__).exception("Failed to send moderation report email")


@require_POST
def report_photo(request, photo_uuid):
    """Anonymous visitors can report — no @login_required."""
    photo = get_object_or_404(
        PilgrimPhoto, uuid=photo_uuid, is_public_on_site=True, hidden_by_staff=False
    )
    ip_hash = _ip_hash(request)

    since = timezone.now() - timedelta(hours=1)
    recent_reports = PhotoReport.objects.filter(reporter_ip_hash=ip_hash, created_at__gte=since).count()
    if recent_reports >= REPORTS_PER_HOUR_PER_IP:
        return JsonResponse(
            {"success": False, "error": "rate_limited",
             "message": "Too many reports from this connection — try again later."},
            status=200,
        )

    reason = request.POST.get("reason", "")
    if reason not in dict(PhotoReport.REASON_CHOICES):
        return JsonResponse(
            {"success": False, "error": "invalid", "message": "Choose a reason."}, status=200
        )

    note = request.POST.get("note", "")[:1000]
    reporter = request.user if request.user.is_authenticated else None

    report = PhotoReport.objects.create(
        photo=photo, reporter=reporter, reporter_ip_hash=ip_hash, reason=reason, note=note,
    )
    apply_auto_hide_policy(photo)
    _send_moderation_email(report)

    return JsonResponse(
        {"success": True, "message": "Thank you — this has been reported to our moderators."}
    )
