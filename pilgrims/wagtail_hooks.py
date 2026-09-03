"""
Admin guard for the single-page "Delete" action on a SacredSitePage.

PilgrimPhoto.site uses on_delete=PROTECT, so Django itself refuses to ever
delete a SacredSitePage with photos attached — but a bare ProtectedError
would render as a 500 in the admin. This intercepts the delete beforehand
and shows the editor a clear message instead.

Unpublishing needs no such guard: UnpublishPageAction only flips `live` to
False and never touches the row, so it can't cascade into a photo delete —
see pilgrims/tests.py for the regression test confirming that.

Known gap: Wagtail's bulk-delete action (multi-select in the page listing)
calls page.delete() directly and does not run the before_delete_page hook,
so a bulk delete that hits a SacredSitePage with photos would still surface
a raw ProtectedError instead of this message. Only the single-page delete
flow is guarded here, matching the phase-2 spec.
"""
from django.shortcuts import redirect
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin import messages
from wagtail.admin.menu import MenuItem

from catalog.models import SacredSitePage

from . import admin_views
from .models import PhotoReport, PilgrimPhoto


@hooks.register("before_delete_page")
def guard_sacred_site_delete(request, page):
    if not isinstance(page, SacredSitePage):
        return None

    count = PilgrimPhoto.objects.filter(site_id=page.pk).count()
    if not count:
        return None

    messages.error(
        request,
        f"Can't delete “{page.title}” — {count} pilgrim photo"
        f"{'s' if count != 1 else ''} attached to this site would be "
        "orphaned. Unpublish the page instead if it shouldn't be public "
        "anymore; pilgrims' photos are unaffected either way.",
    )
    return redirect("wagtailadmin_pages:edit", page.pk)


# --- "Pilgrim Moderation" admin section (phase 4) ---------------------------

@hooks.register("register_admin_urls")
def register_pilgrim_moderation_urls():
    return [
        path("pilgrim-moderation/", admin_views.moderation_queue, name="pilgrim_moderation_queue"),
        path(
            "pilgrim-moderation/<uuid:photo_uuid>/",
            admin_views.moderation_photo_detail,
            name="pilgrim_moderation_photo_detail",
        ),
        path(
            "pilgrim-moderation/<uuid:photo_uuid>/action/",
            admin_views.moderation_action,
            name="pilgrim_moderation_action",
        ),
    ]


class PilgrimModerationMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_active and request.user.is_staff

    def get_context(self, request):
        context = super().get_context(request)
        context["open_report_count"] = PhotoReport.objects.filter(status=PhotoReport.STATUS_OPEN).count()
        return context


@hooks.register("register_admin_menu_item")
def register_pilgrim_moderation_menu_item():
    return PilgrimModerationMenuItem(
        "Pilgrim Moderation",
        reverse("pilgrim_moderation_queue"),
        icon_name="warning",
        order=9000,
    )
