"""Public endpoints for guided pilgrimages. Both exist only while the v2
switch allows it for this request; otherwise they 404 like any unknown URL."""
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from wagtail.models import Page

from catalog.models import SacredSitePage
from core.v2 import v2_enabled

from .models import PENDING_INTEREST_KEY, GuidedPilgrimage, TourClickDaily, TourInterest


@require_GET
def go_tour(request, pk):
    """/go/tour/<id>/?from=<page id>: count the click, then 302 to the operator.

    Records only (tour, page, date, count). Nothing about the visitor is read
    or stored, and the response sets no cookie (no session or CSRF access).
    """
    if not v2_enabled(request):
        raise Http404
    tour = get_object_or_404(GuidedPilgrimage.objects.public().exclude(booking_url__isnull=True)
                             .exclude(booking_url=""), pk=pk)
    page = None
    source = request.GET.get("from", "")
    if source.isdigit():
        page = Page.objects.filter(pk=int(source)).first()
    TourClickDaily.record(tour, page)
    response = HttpResponseRedirect(tour.booking_url)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def tour_interest(request):
    """A pilgrim registers interest in group trips to a site.

    POST only, so no plain link can ever create interest. Signed in: the row
    is created (idempotently). Signed out: the site is parked in the session
    and the visitor is sent to sign in; tours.signals creates the interest
    on sign-in if it is still fresh. Always returns to the page."""
    if not v2_enabled(request):
        raise Http404
    site_id = request.POST.get("site", "")
    if not site_id.isdigit():
        raise Http404
    site = get_object_or_404(SacredSitePage.objects.live(), pk=int(site_id))
    back = site.url + "#guided-pilgrimages"
    if not request.user.is_authenticated:
        request.session[PENDING_INTEREST_KEY] = {"site": site.pk, "at": timezone.now().timestamp()}
        return redirect_to_login(back)
    TourInterest.objects.get_or_create(user=request.user, site=site)
    return HttpResponseRedirect(back)
