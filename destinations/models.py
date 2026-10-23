"""Destination hubs: one page per pilgrimage region (Rome & Vatican City,
Assisi & Umbria, ...) gathering its sacred sites, saints, routes and tours.

DestinationIndexPage lives at /destinations/; DestinationHubPage pages sit
under it. A hub's sites are its curated HubSite rows, in order, plus -- when
include_auto is on -- every other live site matching its countries (by the
approved SacredSitePage.country_code) or localities. Everything else on the
page (saints, tours) is derived from those sites.

The pages render on their own (they are new), but every link into them from
existing pages is behind the v2 switch, and they stay drafts until an
editor publishes them.
"""
from django import forms
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.functional import cached_property
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page

from catalog.countries import COUNTRY_CHOICES, COUNTRY_NAMES
from catalog.models import CATEGORY_STYLES, DEFAULT_CATEGORY_STYLE, SacredSitePage

DEFAULT_PLAN_URL = "/plan/"
MAJOR_SITES_MAX = 12
HUB_TOURS_MAX = 3
MENU_HUBS_MAX = 4
GETTING_AROUND_FEATURES = ["bold", "italic", "link", "ul", "ol"]

COMBINE_MODE_CHOICES = [
    ("drive", "drive"),
    ("train", "train"),
    ("bus", "bus"),
    ("walk", "walk"),
    ("ferry", "ferry"),
    ("other", "other"),
]


class CountryCodesField(ArrayField):
    """ISO 3166-1 codes, edited as a multi-select."""

    def __init__(self, **kwargs):
        kwargs.setdefault("base_field", models.CharField(max_length=2))
        super().__init__(**kwargs)

    def formfield(self, **kwargs):
        return forms.TypedMultipleChoiceField(
            choices=COUNTRY_CHOICES, required=False, label=self.verbose_name.capitalize(),
            widget=forms.SelectMultiple(attrs={"size": 8}),
            help_text="The sites' approved country codes this hub covers.",
        )


class DestinationIndexPage(Page):
    intro = models.TextField(null=True, blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro")]
    parent_page_types = ["home.HomePage"]
    subpage_types = ["destinations.DestinationHubPage"]
    max_count = 1

    class Meta:
        verbose_name = "destination index page"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["hubs"] = DestinationHubPage.objects.child_of(self).live().public().specific()
        return context


class DestinationHubPage(Page):
    intro = models.TextField(null=True, blank=True, help_text="One or two sentences under the title.")
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Used for the homepage destination tile.",
    )
    tile_caption = models.CharField(max_length=60, null=True, blank=True)
    country_codes = CountryCodesField(blank=True, default=list)
    localities = models.TextField(
        null=True, blank=True, help_text="Optional: one locality per line (matched to the sites' locality).",
    )
    include_auto = models.BooleanField(
        default=False,
        help_text="Also include every live site in these countries / localities, after the curated ones.",
    )
    getting_around = RichTextField(null=True, blank=True, features=GETTING_AROUND_FEATURES)
    related_trails = ParentalManyToManyField("catalog.PilgrimageTrailPage", blank=True, related_name="hubs")
    travel_advisory_url = models.URLField(
        max_length=500, null=True, blank=True,
        help_text="This destination's travel advisory; replaces the general one on its sites' pages.",
    )
    plan_link_url = models.CharField(
        max_length=255, null=True, blank=True,
        help_text='"Plan a trip here" target. Leave blank for the trip planner (/plan/).',
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("hero_image"),
        FieldPanel("tile_caption"),
        MultiFieldPanel(
            [
                InlinePanel("hub_sites", label="Site (curated order)"),
                FieldPanel("include_auto"),
                FieldPanel("country_codes"),
                FieldPanel("localities"),
            ],
            heading="Sites",
        ),
        InlinePanel("stay_options", label="Suggested length of stay", max_num=3),
        InlinePanel("combine_with", label="Day trip"),
        FieldPanel("getting_around"),
        FieldPanel("related_trails"),
        FieldPanel("travel_advisory_url"),
        FieldPanel("plan_link_url"),
    ]
    parent_page_types = ["destinations.DestinationIndexPage"]
    subpage_types = []

    class Meta:
        verbose_name = "destination hub page"

    # --- sites -------------------------------------------------------------

    @property
    def locality_list(self):
        return [line.strip().lower() for line in (self.localities or "").splitlines() if line.strip()]

    @cached_property
    def sites(self):
        """Curated sites in order, then (with include_auto) the rest by title.
        Live sites only."""
        curated = [
            row.site for row in self.hub_sites.select_related("site").order_by("sort_order")
            if row.site_id and row.site.live
        ]
        seen = {site.pk for site in curated}
        extra = []
        if self.include_auto and (self.country_codes or self.locality_list):
            for site in SacredSitePage.objects.live().exclude(pk__in=seen).order_by("title"):
                if self.matches(site):
                    extra.append(site)
        return curated + extra

    def matches(self, site):
        """Does this site fall inside the hub's countries/localities? With both
        set, a site must match both (Assisi inside Italy, not Assisi anywhere)."""
        codes = set(self.country_codes or [])
        localities = self.locality_list
        in_country = bool(site.country_code) and site.country_code in codes
        in_locality = bool(site.locality) and site.locality.strip().lower() in localities
        if codes and localities:
            return in_country and in_locality or (in_locality and not site.country_code)
        return in_country if codes else in_locality

    def contains(self, site):
        return any(s.pk == site.pk for s in self.sites)

    @property
    def major_sites(self):
        """Curated, then auto-included sites, up to 12 -- minus any site that is
        listed under Day trips, so no site appears twice on the page."""
        day_trip_ids = {trip.site_id for trip in self.day_trips if trip.site_id}
        return [site for site in self.sites if site.pk not in day_trip_ids][:MAJOR_SITES_MAX]

    def map_payload(self):
        """The hub map's data: live sites with coordinates only."""
        return [
            {
                "title": site.title,
                "category": site.category,
                "line": (site.summary_short or "")[:140],
                "url": site.url,
                "latlng": [float(site.latitude), float(site.longitude)],
            }
            for site in self.sites
            if site.live and site.latitude is not None and site.longitude is not None
        ]

    @property
    def legend(self):
        """[(category, style)] for the categories on the map, in the dict's order."""
        present = {site.category for site in self.sites if site.latitude is not None and site.longitude is not None}
        return [(cat, style) for cat, style in CATEGORY_STYLES.items() if cat in present]

    @property
    def countries_display(self):
        return ", ".join(COUNTRY_NAMES.get(code, code) for code in self.country_codes or [])

    # --- derived "Go deeper" -----------------------------------------------

    @cached_property
    def saints(self):
        """Principal saints of the hub's sites, most sites first."""
        counts, saints = {}, {}
        for site in self.sites:
            saint = site.associated_saint
            if saint is not None and saint.live:
                counts[saint.pk] = counts.get(saint.pk, 0) + 1
                saints[saint.pk] = saint
        return sorted(saints.values(), key=lambda s: (-counts[s.pk], s.title))

    @cached_property
    def trails(self):
        return list(self.related_trails.live().order_by("title"))

    @cached_property
    def tours(self):
        from tours.models import GuidedPilgrimage

        site_ids = [site.pk for site in self.sites]
        if not site_ids:
            return []
        return list(
            GuidedPilgrimage.objects.public().filter(stops__site_id__in=site_ids).distinct()
            .with_next_departure().soonest_first().select_related("operator")
            .prefetch_related("stops__site", "departures")[:HUB_TOURS_MAX]
        )

    @property
    def has_go_deeper(self):
        return bool(self.saints or self.trails or self.tours)

    @property
    def plan_url(self):
        return self.plan_link_url or DEFAULT_PLAN_URL

    @cached_property
    def day_trips(self):
        return list(self.combine_with.select_related("site").all())

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["explore_page"] = Page.objects.live().public().filter(slug="explore").first()
        context["index_page"] = self.get_parent().specific if self.get_parent() else None
        return context


class HubSite(Orderable):
    hub = ParentalKey(DestinationHubPage, on_delete=models.CASCADE, related_name="hub_sites")
    site = models.ForeignKey(SacredSitePage, on_delete=models.CASCADE, related_name="hub_rows")

    panels = [FieldPanel("site")]


class StayOption(Orderable):
    hub = ParentalKey(DestinationHubPage, on_delete=models.CASCADE, related_name="stay_options")
    label = models.CharField(max_length=40, help_text='e.g. "1 day", "2–3 days".')
    text = models.CharField(max_length=300)

    panels = [FieldPanel("label"), FieldPanel("text")]


class CombineWith(Orderable):
    """A day trip from the hub: a site page, or just a place name."""

    hub = ParentalKey(DestinationHubPage, on_delete=models.CASCADE, related_name="combine_with")
    site = models.ForeignKey(SacredSitePage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=120, null=True, blank=True, help_text="Used when there's no site page.")
    reason = models.CharField(max_length=200, null=True, blank=True)
    travel_time = models.CharField(max_length=60, null=True, blank=True, help_text='Hand-entered, e.g. "1 h 30".')
    mode = models.CharField(max_length=10, null=True, blank=True, choices=COMBINE_MODE_CHOICES)

    panels = [FieldPanel("site"), FieldPanel("name"), FieldPanel("reason"), FieldPanel("travel_time"),
              FieldPanel("mode")]

    @property
    def label(self):
        return self.name or (self.site.title if self.site_id else "")

    @property
    def link(self):
        return self.site.url if self.site_id and self.site.live else ""

    @property
    def style(self):
        if self.site_id:
            return CATEGORY_STYLES.get(self.site.category, DEFAULT_CATEGORY_STYLE)
        return None


# --- lookups used by the linking points on other pages ----------------------

def live_hubs():
    return list(DestinationHubPage.objects.live().public().specific().order_by("path"))


def live_hubs_for_site(site):
    return [hub for hub in live_hubs() if hub.contains(site)]


def live_hubs_for_saint(saint):
    hubs = []
    for hub in live_hubs():
        if any(s.associated_saint_id == saint.pk for s in hub.sites):
            hubs.append(hub)
    return hubs
