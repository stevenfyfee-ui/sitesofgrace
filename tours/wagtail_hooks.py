"""Admin for guided pilgrimages: two snippet viewsets and two reports.

Reports are staff-only (view permissions) and show counts only: interest
per site, and "Outbound clicks" -- tours by tour and page, lodging by place
to stay and page -- over the last 30 or 90 days.
"""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Sum
from django.shortcuts import render
from django.urls import path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .models import GuidedPilgrimage, TourClickDaily, TourInterest, TourOperator


class TourOperatorViewSet(SnippetViewSet):
    model = TourOperator
    icon = "group"
    menu_label = "Tour operators"
    list_display = ["name", "catholic_focused", "is_active", "last_verified_on"]
    list_filter = ["is_active", "catholic_focused"]
    search_fields = ["name", "description"]
    search_backend_name = None


class GuidedPilgrimageViewSet(SnippetViewSet):
    model = GuidedPilgrimage
    icon = "site"
    menu_label = "Guided pilgrimages"
    list_display = ["title", "operator", "is_live", "duration_days", "last_verified_on"]
    list_filter = ["is_live", "operator", "travel_style", "is_affiliate_link"]
    search_fields = ["title", "departure_city"]
    search_backend_name = None


class ToursGroup(SnippetViewSetGroup):
    menu_label = "Guided pilgrimages"
    menu_icon = "site"
    menu_order = 260
    items = (GuidedPilgrimageViewSet, TourOperatorViewSet)


register_snippet(ToursGroup)


def interest_report(request):
    if not request.user.has_perm("tours.view_tourinterest"):
        raise PermissionDenied
    rows = (
        TourInterest.objects.values("site_id", "site__title", "site__url_path")
        .annotate(count=Count("id"), latest=Max("created"))
        .order_by("-latest")
    )
    return render(request, "tours/admin/interest_report.html", {"rows": rows, "total": TourInterest.objects.count()})


TOUR_CLICKS_PERM = "tours.view_tourclickdaily"
LODGING_CLICKS_PERM = "catalog.view_lodgingclickdaily"


def outbound_clicks_report(request):
    can_tours = request.user.has_perm(TOUR_CLICKS_PERM)
    can_lodging = request.user.has_perm(LODGING_CLICKS_PERM)
    if not (can_tours or can_lodging):
        raise PermissionDenied
    from catalog.models import LodgingClickDaily

    days = 90 if request.GET.get("days") == "90" else 30
    since = date.today() - timedelta(days=days - 1)
    tour_rows = lodging_rows = None
    if can_tours:
        tour_rows = (
            TourClickDaily.objects.filter(date__gte=since)
            .values("pilgrimage_id", "pilgrimage__title", "page_id", "page__title")
            .annotate(clicks=Sum("count"))
            .order_by("-clicks", "pilgrimage__title")
        )
    if can_lodging:
        lodging_rows = (
            LodgingClickDaily.objects.filter(date__gte=since)
            .values("lodging_id", "lodging__name", "lodging__page__title", "page_id", "page__title")
            .annotate(clicks=Sum("count"))
            .order_by("-clicks", "lodging__name")
        )
    return render(request, "tours/admin/clicks_report.html", {
        "tour_rows": tour_rows, "lodging_rows": lodging_rows, "days": days, "since": since,
    })


@hooks.register("register_admin_urls")
def register_report_urls():
    return [
        path("reports/tour-interest/", interest_report, name="tours_interest_report"),
        path("reports/outbound-clicks/", outbound_clicks_report, name="outbound_clicks_report"),
    ]


class PermissionMenuItem(MenuItem):
    """Shown to users holding any one of `permission` (a name or a tuple)."""

    def __init__(self, *args, permission, **kwargs):
        super().__init__(*args, **kwargs)
        self.permissions = (permission,) if isinstance(permission, str) else tuple(permission)

    def is_shown(self, request):
        return any(request.user.has_perm(p) for p in self.permissions)


@hooks.register("register_reports_menu_item")
def register_interest_report_menu_item():
    return PermissionMenuItem(
        "Group trip interest", reverse("tours_interest_report"), icon_name="group", order=900,
        permission="tours.view_tourinterest",
    )


@hooks.register("register_reports_menu_item")
def register_clicks_report_menu_item():
    return PermissionMenuItem(
        "Outbound clicks", reverse("outbound_clicks_report"), icon_name="link-external", order=901,
        permission=(TOUR_CLICKS_PERM, LODGING_CLICKS_PERM),
    )
