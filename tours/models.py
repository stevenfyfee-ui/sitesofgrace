"""Guided pilgrimages run by tour operators, linked to the sacred sites they visit.

Everything here is edited as Wagtail snippets (tours/wagtail_hooks.py) and
shown on v2 site pages only. One GuidedPilgrimage links to every site it
visits through TourStop, so a single record appears on each of those pages.

Privacy: TourInterest stores only (user, site, created) and is deleted with
the user. TourClickDaily stores only (tour, page, date, count) -- no IP, no
user, no cookie.
"""
from datetime import date

from django import forms
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import IntegrityError, models, transaction
from django.db.models import F, Min, Q
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.models import Orderable

MONTH_CHOICES = [
    (1, "Jan"), (2, "Feb"), (3, "Mar"), (4, "Apr"), (5, "May"), (6, "Jun"),
    (7, "Jul"), (8, "Aug"), (9, "Sep"), (10, "Oct"), (11, "Nov"), (12, "Dec"),
]
TRAVEL_STYLE_CHOICES = [
    ("pilgrimage", "Pilgrimage-focused"),
    ("pilgrimage-sightseeing", "Pilgrimage with sightseeing"),
    ("sightseeing", "Sightseeing tour of religious sites"),
]
PRIEST_CHOICES = [
    ("priest", "Priest travels with group"),
    ("director", "Spiritual director"),
    ("none", "None"),
    ("not-stated", "Not stated"),
]
MASS_CHOICES = [
    ("daily", "Daily Mass"),
    ("most-days", "Mass most days"),
    ("some-days", "Mass some days"),
    ("not-stated", "Not stated"),
]
CONFESSION_CHOICES = [
    ("yes", "Confession offered"),
    ("no", "No Confession"),
    ("not-stated", "Not stated"),
]
ACTIVITY_CHOICES = [
    ("easy", "Easy"),
    ("moderate", "Moderate"),
    ("demanding", "Demanding"),
]
DEPARTURE_STATUS_CHOICES = [
    ("open", "Open"),
    ("limited", "Limited seats"),
    ("sold-out", "Sold out"),
    ("cancelled", "Cancelled"),
]

SITE_PAGE_MAX_TOURS = 3
ELSEWHERE_MAX_TOURS = 2

# A signed-out "I'm interested" click parks the site here in the session; it
# is turned into a TourInterest on sign-in only if that happens within the
# window, so an abandoned sign-in never creates interest later.
PENDING_INTEREST_KEY = "tours_pending_interest"
PENDING_INTEREST_SECONDS = 30 * 60


class MonthsField(ArrayField):
    """Departure months 1-12, edited as a row of checkboxes."""

    def __init__(self, **kwargs):
        kwargs.setdefault("base_field", models.PositiveSmallIntegerField(choices=MONTH_CHOICES))
        super().__init__(**kwargs)

    def formfield(self, **kwargs):
        return forms.TypedMultipleChoiceField(
            choices=MONTH_CHOICES, coerce=int, required=False,
            widget=forms.CheckboxSelectMultiple, label=self.verbose_name.capitalize(),
        )


class TourOperator(models.Model):
    name = models.CharField(max_length=200)
    website = models.URLField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    catholic_focused = models.BooleanField(default=False)
    affiliate_program = models.CharField(max_length=200, null=True, blank=True)
    notes_internal = models.TextField(null=True, blank=True)
    last_verified_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("website"),
        FieldPanel("description"),
        FieldPanel("catholic_focused"),
        FieldPanel("is_active"),
        MultiFieldPanel(
            [FieldPanel("affiliate_program"), FieldPanel("notes_internal"), FieldPanel("last_verified_on")],
            heading="Internal",
        ),
    ]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class GuidedPilgrimageQuerySet(models.QuerySet):
    def public(self):
        """Live tours from active operators."""
        return self.filter(is_live=True, operator__is_active=True)

    def with_next_departure(self, today=None):
        """Annotate next_departure: the soonest upcoming departure that isn't
        cancelled. Past departures never count."""
        today = today or date.today()
        return self.annotate(
            next_departure=Min(
                "departures__depart_date",
                filter=Q(departures__depart_date__gte=today) & ~Q(departures__status="cancelled"),
            )
        )

    def soonest_first(self):
        return self.order_by(F("next_departure").asc(nulls_last=True), "title")


class GuidedPilgrimage(ClusterableModel):
    title = models.CharField(max_length=200)
    operator = models.ForeignKey(TourOperator, on_delete=models.PROTECT, related_name="pilgrimages")
    travel_style = models.CharField(max_length=30, null=True, blank=True, choices=TRAVEL_STYLE_CHOICES)
    duration_days = models.PositiveSmallIntegerField(null=True, blank=True)
    departure_city = models.CharField(max_length=120, null=True, blank=True)
    departure_months = MonthsField(blank=True, default=list)
    price_note = models.CharField(max_length=200, null=True, blank=True)
    priest_or_director = models.CharField(max_length=20, null=True, blank=True, choices=PRIEST_CHOICES)
    mass = models.CharField(max_length=20, null=True, blank=True, choices=MASS_CHOICES)
    confession_offered = models.CharField(max_length=20, null=True, blank=True, choices=CONFESSION_CHOICES)
    hotels_meals = models.CharField(max_length=200, null=True, blank=True)
    activity_level = models.CharField(max_length=20, null=True, blank=True, choices=ACTIVITY_CHOICES)
    group_size_max = models.PositiveSmallIntegerField(null=True, blank=True)
    cancellation_summary = models.TextField(null=True, blank=True)
    booking_url = models.URLField(max_length=500, null=True, blank=True)
    is_affiliate_link = models.BooleanField(
        default=False, help_text="The booking link earns a commission (adds the sponsored rel and disclosure).",
    )
    last_verified_on = models.DateField(null=True, blank=True, help_text="Admin only; never shown publicly.")
    is_live = models.BooleanField(default=False, help_text="Show on site pages (v2).")

    objects = GuidedPilgrimageQuerySet.as_manager()

    panels = [
        FieldPanel("title"),
        FieldPanel("operator"),
        FieldPanel("is_live"),
        FieldPanel("travel_style"),
        InlinePanel("stops", label="Stop"),
        MultiFieldPanel(
            [
                FieldPanel("duration_days"),
                FieldPanel("departure_city"),
                FieldPanel("departure_months"),
                FieldPanel("price_note"),
                FieldPanel("priest_or_director"),
                FieldPanel("mass"),
                FieldPanel("confession_offered"),
                FieldPanel("hotels_meals"),
                FieldPanel("activity_level"),
                FieldPanel("group_size_max"),
                FieldPanel("cancellation_summary"),
            ],
            heading="Facts",
        ),
        InlinePanel("departures", label="Departure"),
        MultiFieldPanel(
            [FieldPanel("booking_url"), FieldPanel("is_affiliate_link"), FieldPanel("last_verified_on")],
            heading="Booking",
        ),
    ]

    class Meta:
        ordering = ["title"]
        verbose_name = "guided pilgrimage"

    def __str__(self):
        return self.title

    @property
    def is_sample(self):
        return "(sample)" in self.title or "(sample)" in self.operator.name

    @property
    def link_rel(self):
        """Standing Rule 9: affiliate links are sponsored."""
        return "sponsored nofollow noopener" if self.is_affiliate_link else "nofollow noopener"

    def upcoming_departures(self, today=None):
        today = today or date.today()
        return [
            d for d in self.departures.all()
            if d.depart_date >= today and d.status != "cancelled"
        ]

    @property
    def months_display(self):
        labels = dict(MONTH_CHOICES)
        return ", ".join(labels[m] for m in sorted(self.departure_months or []) if m in labels)

    def facts(self):
        """The card's eight facts as (label, value); empty facts are left out."""
        departs = " · ".join(part for part in (self.months_display, self.departure_city) if part)
        upcoming = self.upcoming_departures()
        next_dep = upcoming[0] if upcoming else None
        if next_dep:
            departs = " · ".join(part for part in (f"Next {next_dep.depart_date:%b} {next_dep.depart_date.day}, {next_dep.depart_date.year}", departs) if part)
        mass_confession = "; ".join(
            part for part in (
                self.get_mass_display() if self.mass else "",
                self.get_confession_offered_display() if self.confession_offered else "",
            ) if part
        )
        price = self.price_note or ""
        if next_dep and next_dep.price is not None:
            amount = (f"${next_dep.price:,.0f}" if (next_dep.currency or "").upper() == "USD"
                      else f"{next_dep.price:,.0f} {next_dep.currency or ''}".strip())
            price = f"From {amount}" + (f" · {price}" if price else "")
        if next_dep and next_dep.airfare_included:
            price = " · ".join(part for part in (price, "Airfare included") if part)
        facts = [
            ("Length", f"{self.duration_days} days" if self.duration_days else ""),
            ("Departs", departs),
            ("Spiritual director", self.get_priest_or_director_display() if self.priest_or_director else ""),
            ("Mass & Confession", mass_confession),
            ("Hotels & meals", self.hotels_meals or ""),
            ("Activity", self.get_activity_level_display() if self.activity_level else ""),
            ("Group size", f"Up to {self.group_size_max}" if self.group_size_max else ""),
            ("Price", price),
        ]
        return [(label, value) for label, value in facts if value]


class TourStop(Orderable):
    pilgrimage = ParentalKey(GuidedPilgrimage, on_delete=models.CASCADE, related_name="stops")
    site = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True, on_delete=models.SET_NULL, related_name="tour_stops",
    )
    place_name = models.CharField(
        max_length=200, null=True, blank=True, help_text="Used when the stop has no sacred site page.",
    )

    panels = [FieldPanel("site"), FieldPanel("place_name")]

    @property
    def label(self):
        if self.site_id and self.site.live:
            return self.site.title
        return self.place_name or (self.site.title if self.site_id else "")

    @property
    def link(self):
        """The site page's URL, only when the stop is a live page."""
        return self.site.url if self.site_id and self.site.live else ""


class TourDeparture(Orderable):
    pilgrimage = ParentalKey(GuidedPilgrimage, on_delete=models.CASCADE, related_name="departures")
    depart_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, null=True, blank=True)
    airfare_included = models.BooleanField(null=True, blank=True)
    status = models.CharField(max_length=20, null=True, blank=True, choices=DEPARTURE_STATUS_CHOICES)

    panels = [
        FieldPanel("depart_date"), FieldPanel("return_date"), FieldPanel("price"),
        FieldPanel("currency"), FieldPanel("airfare_included"), FieldPanel("status"),
    ]

    class Meta(Orderable.Meta):
        ordering = ["depart_date"]


class TourInterest(models.Model):
    """A signed-in pilgrim asking for group trips to a site. Counted per site
    for operator outreach; never emailed, never shown publicly."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tour_interests")
    site = models.ForeignKey("catalog.SacredSitePage", on_delete=models.CASCADE, related_name="tour_interests")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "site"], name="unique_tour_interest_per_user_site")]
        ordering = ["-created"]


class TourClickDaily(models.Model):
    """Outbound "View on operator site" clicks, one row per tour, page and
    day. Deliberately nothing about who clicked."""

    pilgrimage = models.ForeignKey(GuidedPilgrimage, on_delete=models.CASCADE, related_name="click_days")
    page = models.ForeignKey("wagtailcore.Page", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pilgrimage", "page", "date"], name="unique_tour_click_day"),
            models.UniqueConstraint(
                fields=["pilgrimage", "date"], condition=Q(page__isnull=True), name="unique_tour_click_day_no_page",
            ),
        ]

    @classmethod
    def record(cls, pilgrimage, page=None, day=None):
        """Add one click for (tour, page, day), safely under concurrency."""
        day = day or date.today()
        lookup = {"pilgrimage": pilgrimage, "page": page, "date": day}
        if cls.objects.filter(**lookup).update(count=F("count") + 1):
            return
        try:
            with transaction.atomic():
                cls.objects.create(count=1, **lookup)
        except IntegrityError:
            cls.objects.filter(**lookup).update(count=F("count") + 1)


def tours_for_site(site, limit=SITE_PAGE_MAX_TOURS):
    """Live tours with a stop at this site, soonest upcoming departure first."""
    return list(
        GuidedPilgrimage.objects.public()
        .filter(stops__site=site)
        .distinct()
        .with_next_departure()
        .soonest_first()
        .select_related("operator")
        .prefetch_related("stops__site", "departures")[:limit]
    )


def tours_elsewhere(site, country, limit=ELSEWHERE_MAX_TOURS):
    """Live tours visiting other sites in the same country that do NOT stop
    at this site. Phase 4 swaps country for the destination hub."""
    if not country:
        return []
    return list(
        GuidedPilgrimage.objects.public()
        .filter(Q(stops__site__country=country) | Q(stops__site__country__startswith=country + " ("))
        .exclude(stops__site=site)
        .distinct()
        .with_next_departure()
        .soonest_first()
        .select_related("operator")[:limit]
    )
