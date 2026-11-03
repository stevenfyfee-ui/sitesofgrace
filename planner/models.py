import json
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.http import Http404
from django.utils.text import slugify
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from wagtail.models import Orderable, Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.snippets.models import register_snippet
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

REGION_CHOICES = [
    ("North America", "North America"),
    ("Latin America", "Latin America"),
    ("Western Europe", "Western Europe"),
    ("Southern Europe", "Southern Europe"),
    ("Ireland & UK", "Ireland & UK"),
    ("Eastern Europe", "Eastern Europe"),
    ("Holy Land", "Holy Land"),
]


# Slugs that don't follow slugify(city). Used by the backfill migration and
# by save() when a new destination arrives without a slug.
DESTINATION_SLUG_OVERRIDES = {
    "Mexico City (Guadalupe)": "mexico-city",
}


def destination_slug_for(city):
    return DESTINATION_SLUG_OVERRIDES.get(city) or slugify(city)


@register_snippet
class DestinationCost(ClusterableModel):
    city = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=140, unique=True, null=True, blank=True,
        help_text="Used in trip planner links (e.g. rome-vatican-city). Filled from the city if left blank.",
    )
    country = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=40, choices=REGION_CHOICES)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    nearest_airport_iata = models.CharField(max_length=8, blank=True)
    nearest_airport_name = models.CharField(max_length=160, blank=True)
    gateway_airport_iata = models.CharField(
        max_length=8, null=True, blank=True,
        help_text="International gateway, e.g. FCO for Assisi. Departure uses this when set, "
                  "otherwise the nearest airport.",
    )
    gateway_airport_name = models.CharField(max_length=160, null=True, blank=True)
    hotel_night_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    meal_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    local_transport_day_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    taxi_typical_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    associated_sites = models.ManyToManyField(
        "catalog.SacredSitePage", blank=True, related_name="destination_costs"
    )
    notes = models.TextField(blank=True)

    panels = [
        FieldPanel("city"),
        FieldPanel("slug"),
        FieldPanel("country"),
        FieldPanel("region"),
        MultiFieldPanel(
            [FieldPanel("latitude"), FieldPanel("longitude")],
            heading="Location",
        ),
        FieldPanel("nearest_airport_iata"),
        FieldPanel("nearest_airport_name"),
        FieldPanel("gateway_airport_iata"),
        FieldPanel("gateway_airport_name"),
        FieldPanel("hotel_night_usd"),
        FieldPanel("meal_usd"),
        FieldPanel("local_transport_day_usd"),
        FieldPanel("taxi_typical_usd"),
        FieldPanel("associated_sites"),
        InlinePanel("plan_days", heading="Curated plan", label="Day"),
        FieldPanel("notes"),
    ]

    class Meta:
        ordering = ["city"]

    def __str__(self):
        return self.city

    def save(self, *args, **kwargs):
        # Only ever fills a blank slug; an editor's slug is never rewritten.
        if not self.slug:
            self.slug = destination_slug_for(self.city) or None
        super().save(*args, **kwargs)

    @property
    def departure_airport(self):
        """(iata, name) to fly home from: the gateway when set, else the nearest airport."""
        if self.gateway_airport_iata:
            return self.gateway_airport_iata, self.gateway_airport_name or ""
        return self.nearest_airport_iata, self.nearest_airport_name


class DestinationPlanDay(Orderable):
    """One row of a destination's curated plan: a title plus the sacred
    sites that day covers. Places without a page go in extra_places."""

    destination = ParentalKey(DestinationCost, on_delete=models.CASCADE, related_name="plan_days")
    title = models.CharField(max_length=120)
    sites = ParentalManyToManyField(
        "catalog.SacredSitePage", blank=True, related_name="destination_plan_days",
        limit_choices_to={"live": True},
    )
    extra_places = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Places on this day that have no sacred site page, e.g. \"Lunch in Piazza Navona\".",
    )

    panels = [FieldPanel("title"), FieldPanel("sites"), FieldPanel("extra_places")]

    def __str__(self):
        return self.title


@register_snippet
class RegionFlightAssumption(models.Model):
    region = models.CharField(max_length=40, choices=REGION_CHOICES, unique=True)
    avg_roundtrip_usd_from_us = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    panels = [
        FieldPanel("region"),
        FieldPanel("avg_roundtrip_usd_from_us"),
        FieldPanel("notes"),
    ]

    def __str__(self):
        return self.region


@register_setting
class CalculatorDefaults(BaseGenericSetting):
    default_party_size = models.PositiveIntegerField(default=2)
    default_nights = models.PositiveIntegerField(default=5)
    meals_per_day = models.PositiveIntegerField(default=3)
    people_per_room = models.PositiveIntegerField(default=2)
    hotel_tier_budget_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=0.70)
    hotel_tier_midrange_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.00)
    hotel_tier_comfort_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=1.60)
    misc_buffer_percent = models.PositiveIntegerField(default=12)
    inter_destination_hop_usd = models.DecimalField(max_digits=8, decimal_places=2, default=150)
    currency = models.CharField(max_length=8, default="USD")

    panels = [
        FieldPanel("default_party_size"),
        FieldPanel("default_nights"),
        FieldPanel("meals_per_day"),
        FieldPanel("people_per_room"),
        FieldPanel("hotel_tier_budget_multiplier"),
        FieldPanel("hotel_tier_midrange_multiplier"),
        FieldPanel("hotel_tier_comfort_multiplier"),
        FieldPanel("misc_buffer_percent"),
        FieldPanel("inter_destination_hop_usd"),
        FieldPanel("currency"),
    ]

    class Meta:
        verbose_name = "Trip calculator defaults"


@register_setting
class PlannerSettings(BaseGenericSetting):
    show_booking_links = models.BooleanField(
        default=False,
        help_text="Show the booking card and /go/planner/ links. Can't be turned on until the "
                  "Affiliate Disclosure page is live.",
    )
    max_stops = models.PositiveSmallIntegerField(
        default=6, validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="The most stops one trip can have.",
    )

    panels = [FieldPanel("show_booking_links"), FieldPanel("max_stops")]

    class Meta:
        verbose_name = "Trip planner"

    def clean(self):
        super().clean()
        from planner.booking import affiliate_disclosure_live

        if self.show_booking_links and not affiliate_disclosure_live():
            raise ValidationError({
                "show_booking_links": "Publish the Affiliate Disclosure page before turning on booking links.",
            })


BOOKING_PLACEHOLDERS = ("dest_slug", "iata", "sub_id")
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")


@register_snippet
class PlannerBookingLink(models.Model):
    """An affiliate booking link on the planner's booking card. Visitors
    reach it through /go/planner/<id>/, which counts the click and fills the
    placeholders."""

    label = models.CharField(max_length=80)
    provider = models.CharField(max_length=80)
    url_template = models.CharField(
        max_length=500,
        help_text="https:// link. May use {dest_slug}, {iata} and {sub_id}; they are filled "
                  "from the trip's first stop.",
    )
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    panels = [
        FieldPanel("label"),
        FieldPanel("provider"),
        FieldPanel("url_template"),
        FieldPanel("sort_order"),
        FieldPanel("active"),
    ]

    class Meta:
        ordering = ["sort_order", "label"]
        verbose_name = "planner booking link"

    def __str__(self):
        return f"{self.label} ({self.provider})"

    def clean(self):
        super().clean()
        if not (self.url_template or "").startswith("https://"):
            raise ValidationError({"url_template": "The link must start with https://."})
        unknown = sorted(set(_PLACEHOLDER_RE.findall(self.url_template)) - set(BOOKING_PLACEHOLDERS))
        if unknown:
            raise ValidationError({
                "url_template": "Unknown placeholder(s): " + ", ".join("{%s}" % u for u in unknown)
                                + ". Use {dest_slug}, {iata} or {sub_id}.",
            })


TIER_CHOICES = [("budget", "Budget"), ("mid", "Mid-range"), ("comfort", "Comfort")]
PACE_CHOICES = [(2, "Unhurried"), (3, "Balanced"), (4, "Full days")]
PARTY_MIN, PARTY_MAX = 1, 12
NIGHTS_MIN, NIGHTS_MAX = 1, 21


class Trip(models.Model):
    """A pilgrim's saved plan. Only the inputs are stored; the itinerary and
    budget are rebuilt from current data every time (planner/itinerary.py)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips")
    title = models.CharField(max_length=120)
    start_date = models.DateField(null=True, blank=True)
    party = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(PARTY_MIN), MaxValueValidator(PARTY_MAX)],
    )
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, default="mid")
    pace = models.PositiveSmallIntegerField(choices=PACE_CHOICES, default=3)
    share_token = models.CharField(max_length=32, null=True, blank=True, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated"]
        indexes = [
            # Backs the save rate limit's filter(owner=X, updated__gte=Y).
            models.Index(fields=["owner", "updated"]),
        ]

    def __str__(self):
        return self.title


class TripStop(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    destination = models.ForeignKey(DestinationCost, on_delete=models.PROTECT, related_name="trip_stops")
    nights = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(NIGHTS_MIN), MaxValueValidator(NIGHTS_MAX)],
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class PlanPage(RoutablePageMixin, Page):
    heading = models.CharField(max_length=200, blank=True)
    intro = RichTextField(blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    disclaimer = RichTextField(
        blank=True,
        default=(
            "<p>These numbers are estimates to help you plan, not a price quote. "
            "Real costs change with the season, how far ahead you book, and where "
            "you're traveling from. Use this as a starting point, then confirm "
            "prices before you book.</p>"
        ),
        help_text=(
            "No longer shown on the site. The trip calculator now shows plan_estimate "
            "from Settings > Legal notices."
        ),
    )

    content_panels = Page.content_panels + [
        FieldPanel("heading"),
        FieldPanel("hero_image"),
        FieldPanel("intro"),
        FieldPanel("disclaimer"),
    ]

    max_count = 1

    V2_TEMPLATE = "planner/v2/page.html"

    def get_template(self, request, *args, **kwargs):
        from core.v2 import planner_v2_enabled
        if planner_v2_enabled(request):
            return self.V2_TEMPLATE
        return super().get_template(request, *args, **kwargs)

    def get_context(self, request, *args, **kwargs):
        # Trip Planner v2 (SOG_PLANNER_V2). With the switch off, everything
        # below this branch is the old estimator, untouched; test_flag_off.py
        # proves /plan/ is byte-identical to main.
        from core.v2 import planner_v2_enabled
        if planner_v2_enabled(request):
            from planner.page import page_context
            context = super().get_context(request, *args, **kwargs)
            context.update(page_context(request, self))
            return context
        context = super().get_context(request)
        from planner.models import (
            CalculatorDefaults, DestinationCost, RegionFlightAssumption,
        )
        defaults = CalculatorDefaults.load(request_or_site=request)
        destinations = [
            {
                "id": d.id, "city": d.city, "country": d.country, "region": d.region,
                "airport": d.nearest_airport_iata, "airport_name": d.nearest_airport_name,
                "hotel": float(d.hotel_night_usd), "meal": float(d.meal_usd),
                "transport": float(d.local_transport_day_usd), "taxi": float(d.taxi_typical_usd),
            }
            for d in DestinationCost.objects.all()
        ]

        selected_id = None
        site_slug = request.GET.get("site")
        if site_slug:
            from catalog.models import SacredSitePage
            site = SacredSitePage.objects.live().filter(slug=site_slug).first()
            if site:
                dc = self._match_destination(site)
                if dc:
                    selected_id = dc.id

        journey_destinations = []
        if request.user.is_authenticated:
            from pilgrims.models import SiteVisit
            seen = set()
            for visit in SiteVisit.objects.filter(owner=request.user).select_related("site"):
                dc = self._match_destination(visit.site)
                if dc and dc.id not in seen:
                    seen.add(dc.id)
                    journey_destinations.append({"id": dc.id, "city": dc.city})
            if selected_id is None and journey_destinations:
                selected_id = journey_destinations[0]["id"]

        context["journey_destinations"] = journey_destinations
        from planner import pricing
        context["booking_links"] = pricing.booking_links(None)
        context["plan_data"] = {
            "destinations": destinations,
            "region_flights": {
                r.region: float(r.avg_roundtrip_usd_from_us)
                for r in RegionFlightAssumption.objects.all()
            },
            "defaults": {
                "party": defaults.default_party_size,
                "nights": defaults.default_nights,
                "meals_per_day": defaults.meals_per_day,
                "people_per_room": defaults.people_per_room,
                "budget": float(defaults.hotel_tier_budget_multiplier),
                "mid": float(defaults.hotel_tier_midrange_multiplier),
                "comfort": float(defaults.hotel_tier_comfort_multiplier),
                "misc_pct": defaults.misc_buffer_percent,
                "hop": float(defaults.inter_destination_hop_usd),
                "currency": defaults.currency,
            },
            "selected_id": selected_id,
        }
        return context

    def _match_destination(self, site):
        """Resolve a SacredSitePage to a DestinationCost: explicit M2M link
        first, then a locality/city name match."""
        from planner.api import destination_for_site
        return destination_for_site(site)

    # --- Trip Planner v2 routes (JSON responses). Each 404s unless SOG_PLANNER_V2 allows the
    # request (core.v2.planner_v2_enabled). planner/tests/test_routes.py
    # checks every one, so a merge can't drop RoutablePageMixin silently.

    def _require_v2(self, request):
        from core.v2 import planner_v2_enabled
        if not planner_v2_enabled(request):
            raise Http404

    @path("build/", name="build_json")
    def build_json_route(self, request):
        self._require_v2(request)
        from planner.api import build_json
        return build_json(request)

    @path("search/", name="search_json")
    def search_json_route(self, request):
        self._require_v2(request)
        from planner.api import search_json
        return search_json(request)

    @path("trips/", name="my_trips")
    def my_trips_route(self, request):
        self._require_v2(request)
        from planner import trips
        return trips.my_trips(request, self)

    @path("trips/save/", name="trip_save")
    def trip_save_route(self, request):
        self._require_v2(request)
        from planner import trips
        return trips.save(request, self)

    @path("trips/<int:trip_id>/rename/", name="trip_rename")
    def trip_rename_route(self, request, trip_id):
        self._require_v2(request)
        from planner import trips
        return trips.rename(request, self, trip_id)

    @path("trips/<int:trip_id>/delete/", name="trip_delete")
    def trip_delete_route(self, request, trip_id):
        self._require_v2(request)
        from planner import trips
        return trips.delete(request, self, trip_id)

    @path("trips/<int:trip_id>/share/", name="trip_share")
    def trip_share_route(self, request, trip_id):
        self._require_v2(request)
        from planner import trips
        return trips.share(request, self, trip_id)

    @path("t/<str:token>/", name="shared_trip")
    def shared_trip_route(self, request, token):
        self._require_v2(request)
        from planner import trips
        return trips.shared(request, self, token)
