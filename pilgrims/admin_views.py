"""
"Pilgrim Moderation" — a Wagtail admin section, not a pilgrims/ URL.

Two views on purpose: the queue lists reports (no photo bytes rendered —
metadata only: reason, note, owner, site, other-report counts), and the
per-photo detail view is the ONE place staff actually see the image. That
split exists because viewing the image is the one deliberate exception to
"staff get no bypass" (permissions.staff_can_view_reported_photo), and that
function both gates AND logs — so only the view that needs to show the
photo ever calls it, not the queue listing.
"""
from django.contrib import messages as admin_messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import sharing
from .models import ModerationAction, PhotoReport, PilgrimPhoto
from .permissions import staff_can_view_reported_photo


def _is_staff(user):
    return user.is_authenticated and user.is_staff


staff_required = user_passes_test(_is_staff, login_url="wagtailadmin_login")


@staff_required
def moderation_queue(request):
    open_reports = (
        PhotoReport.objects.filter(status=PhotoReport.STATUS_OPEN)
        .select_related("photo", "photo__owner", "photo__owner__pilgrim", "photo__site", "reporter")
        .order_by("-created_at")
    )
    photo_ids = {report.photo_id for report in open_reports}
    report_counts = {
        row["photo_id"]: row["n"]
        for row in PhotoReport.objects.filter(photo_id__in=photo_ids)
        .values("photo_id")
        .annotate(n=Count("id"))
    }
    for report in open_reports:
        report.total_reports_on_photo = report_counts.get(report.photo_id, 1)

    return render(request, "pilgrimsadmin/moderation_queue.html", {"open_reports": open_reports})


@staff_required
def moderation_photo_detail(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid)
    if not staff_can_view_reported_photo(request.user, photo):
        raise Http404

    reports = (
        PhotoReport.objects.filter(photo=photo).select_related("reporter").order_by("-created_at")
    )
    other_reports_same_owner = (
        PhotoReport.objects.filter(photo__owner=photo.owner, status=PhotoReport.STATUS_OPEN)
        .exclude(photo=photo)
        .select_related("photo")
    )
    return render(request, "pilgrimsadmin/moderation_photo_detail.html", {
        "photo": photo,
        "reports": reports,
        "other_reports_same_owner": other_reports_same_owner,
    })


@staff_required
@require_POST
def moderation_action(request, photo_uuid):
    photo = get_object_or_404(PilgrimPhoto, uuid=photo_uuid)
    action = request.POST.get("action")

    if action == "hide":
        reason = request.POST.get("reason", "").strip() or "Hidden by staff."
        sharing.hide_photo(photo, reason=reason)
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_HIDE,
            photo=photo, owner_affected=photo.owner, note=reason,
        )
        admin_messages.success(request, "Photo hidden.")

    elif action == "unhide":
        sharing.unhide_photo(photo)
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_UNHIDE,
            photo=photo, owner_affected=photo.owner,
        )
        admin_messages.success(request, "Photo unhidden.")

    elif action == "dismiss_report":
        report = get_object_or_404(PhotoReport, pk=request.POST.get("report_id"), photo=photo)
        report.status = PhotoReport.STATUS_DISMISSED
        report.handled_by = request.user
        report.handled_at = timezone.now()
        report.save(update_fields=["status", "handled_by", "handled_at"])
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_DISMISS_REPORT,
            photo=photo, report=report, owner_affected=photo.owner,
        )
        admin_messages.success(request, "Report dismissed.")

    elif action == "delete_photo":
        owner = photo.owner
        photo_uuid_str = str(photo.uuid)
        # Written BEFORE delete(); PilgrimPhoto FK is on_delete=SET_NULL
        # specifically so this row survives (with the photo reference
        # nulled) rather than cascading away with the photo it documents.
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_DELETE_PHOTO,
            photo=photo, owner_affected=owner, note=f"Deleted photo {photo_uuid_str}",
        )
        photo.delete()
        admin_messages.success(request, "Photo deleted.")
        return redirect("pilgrim_moderation_queue")

    elif action == "suspend_sharing":
        profile = photo.owner.pilgrim
        profile.can_share_publicly = False
        profile.save(update_fields=["can_share_publicly"])
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_SUSPEND_SHARING,
            photo=photo, owner_affected=photo.owner,
        )
        admin_messages.success(request, f"{photo.owner.pilgrim.handle}'s public sharing is suspended.")

    elif action == "reinstate_sharing":
        profile = photo.owner.pilgrim
        profile.can_share_publicly = True
        profile.save(update_fields=["can_share_publicly"])
        ModerationAction.objects.create(
            actor=request.user, action=ModerationAction.ACTION_REINSTATE_SHARING,
            photo=photo, owner_affected=photo.owner,
        )
        admin_messages.success(request, f"{photo.owner.pilgrim.handle}'s public sharing is reinstated.")

    else:
        admin_messages.error(request, "Unknown moderation action.")

    # The public gallery's one-click staff "Hide" button posts here with a
    # `next` back to the gallery page it was clicked from; every other
    # caller (the moderation admin templates) omits it and lands back on
    # the photo's moderation detail page as before.
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("pilgrim_moderation_photo_detail", photo_uuid=photo.uuid)
