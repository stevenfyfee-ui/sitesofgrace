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
from wagtail import hooks
from wagtail.admin import messages

from catalog.models import SacredSitePage

from .models import PilgrimPhoto


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
