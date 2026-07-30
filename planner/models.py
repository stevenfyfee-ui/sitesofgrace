import json

from django.db import models
from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
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


@register_snippet
class DestinationCost(models.Model):
    city = models.CharField(max_length=120)
    country = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=40, choices=REGION_CHOICES)
    nearest_airport_iata = models.CharField(max_length=8, blank=True)
    nearest_airport_name = models.CharField(max_length=160, blank=True)
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
        FieldPanel("country"),
        FieldPanel("region"),
        FieldPanel("nearest_airport_iata"),
        FieldPanel("nearest_airport_name"),
        FieldPanel("hotel_night_usd"),
        FieldPanel("meal_usd"),
        FieldPanel("local_transport_day_usd"),
        FieldPanel("taxi_typical_usd"),
        FieldPanel("associated_sites"),
        FieldPanel("notes"),
    ]

    class Meta:
        ordering = ["city"]

    def __str__(self):
        return self.city


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


class PlanPage(Page):
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
    )

    content_panels = Page.content_panels + [
        FieldPanel("heading"),
        FieldPanel("hero_image"),
        FieldPanel("intro"),
        FieldPanel("disclaimer"),
    ]

    max_count = 1

    def get_context(self, request):
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
            from community.models import JourneyEntry
            seen = set()
            for entry in JourneyEntry.objects.filter(user=request.user).select_related("site"):
                dc = self._match_destination(entry.site)
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
        from planner.models import DestinationCost
        dc = DestinationCost.objects.filter(associated_sites=site).first()
        if dc:
            return dc
        locality = (getattr(site, "locality", "") or "").strip()
        if locality:
            dc = DestinationCost.objects.filter(city__iexact=locality).first()
            if dc:
                return dc
            low = locality.lower()
            for cand in DestinationCost.objects.all():
                cl = cand.city.lower()
                if cl in low or low in cl:
                    return cand
        return None
