from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.utils.functional import cached_property
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, route
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page
from wagtail.snippets.models import register_snippet

from catalog.travel_sections import (
    TRAVEL_CLUSTERS,
    TRAVEL_LABELS,
    TRAVEL_SECTION_CHOICES,
)

GALLERY_PREVIEW_COUNT = 8
GALLERY_PAGE_SIZE = 24

CATEGORY_CHOICES = [
    ("Marian Apparition", "Marian Apparition"),
    ("Eucharistic Miracle", "Eucharistic Miracle"),
    ("Saints & Tombs", "Saints & Tombs"),
    ("Holy Land", "Holy Land"),
    ("Shrine & Basilica", "Shrine & Basilica"),
]

# Single source of truth for per-category colors, mirrored in the interactive
# map's CATEGORY_STYLES JS object (home/templates/home/map_page.html) so pins,
# legend swatches, and category chips/tiles elsewhere on the site all agree.
CATEGORY_STYLES = {
    "Marian Apparition":   {"fill": "#FDF9F2", "stroke": "#032553", "dot": "#032553"},
    "Eucharistic Miracle": {"fill": "#C79A42", "stroke": "#C79A42", "dot": "#FDF9F2"},
    "Saints & Tombs":      {"fill": "#032553", "stroke": "#032553", "dot": "#C79A42"},
    "Holy Land":           {"fill": "#F9F1E8", "stroke": "#C79A42", "dot": "#C79A42"},
    "Shrine & Basilica":   {"fill": "#173A61", "stroke": "#173A61", "dot": "#FDF9F2"},
}
DEFAULT_CATEGORY_STYLE = {"fill": "#173A61", "stroke": "#173A61", "dot": "#FDF9F2"}

MAP_PAGE_SLUG = "interactive-map"

# Where pilgrimage trails are filed in the page tree. The Explore hub already
# carries a "Pilgrimage Routes" card; it stays unclickable until this page has
# a live child (see home.StandardPage._hub_card_is_clickable).
TRAILS_PARENT_SLUG = "pilgrimage-routes"

# Trail line colors, mirrored in the map JS via the trails JSON payload rather
# than duplicated there -- the server sends the hex, so this dict is the only
# place a color is written down. Kept inside the brand palette so a trail line
# never fights the category pins it runs between.
TRAIL_COLORS = {
    "gold":       "#C79A42",
    "navy":       "#032553",
    "slate":      "#173A61",
    "terracotta": "#A65A3A",
    "olive":      "#6B7B4A",
    "plum":       "#6A4568",
}
TRAIL_COLOR_CHOICES = [
    ("gold", "Gold"),
    ("navy", "Navy"),
    ("slate", "Slate blue"),
    ("terracotta", "Terracotta"),
    ("olive", "Olive"),
    ("plum", "Plum"),
]
DEFAULT_TRAIL_COLOR = "gold"

TRAIL_TYPE_CHOICES = [
    ("Walking route", "Walking route"),
    ("Driving route", "Driving route"),
    ("Mixed route", "Mixed route"),
    ("Devotional route", "Devotional route"),
]

CANONICAL_STATUS_CHOICES = [
    ("Nihil obstat", "Nihil obstat"),
    ("Prae oculis habeatur", "Prae oculis habeatur"),
    ("Curatur", "Curatur"),
    ("Sub mandato", "Sub mandato"),
    ("Prohibetur", "Prohibetur"),
    ("Declaratio de non supernaturalitate", "Declaratio de non supernaturalitate"),
    ("Not Applicable", "Not Applicable"),
    ("Recognized Devotion", "Recognized Devotion"),
    ("Constat de supernaturalitate (legacy)", "Constat de supernaturalitate (legacy)"),
]


@register_snippet
class Topic(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
    ]

    def __str__(self):
        return self.name


class SaintPage(Page):
    also_known_as = models.CharField(max_length=255, blank=True)
    honorific_type = models.CharField(max_length=255, blank=True)
    feast_day = models.CharField(max_length=120, blank=True)
    born = models.CharField(max_length=160, blank=True)
    died = models.CharField(max_length=160, blank=True)
    canonized = models.CharField(max_length=200, blank=True)
    patronage = models.TextField(blank=True)
    significance = models.TextField(blank=True)
    body = RichTextField(blank=True)
    portrait = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    topics = ParentalManyToManyField("catalog.Topic", blank=True, related_name="saints")
    source_url = models.URLField(blank=True)
    source_note = models.CharField(max_length=255, blank=True)
    data_status = models.CharField(max_length=40, blank=True)
    editor_notes = models.TextField(blank=True)
    religious_order = models.CharField(max_length=160, blank=True)
    burial_place = models.CharField(max_length=200, blank=True)
    wikidata_id = models.CharField(max_length=16, blank=True)
    portrait_url = models.URLField(max_length=500, blank=True)
    portrait_credit = models.CharField(max_length=255, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("portrait"),
        MultiFieldPanel(
            [
                FieldPanel("also_known_as"),
                FieldPanel("honorific_type"),
                FieldPanel("feast_day"),
                FieldPanel("born"),
                FieldPanel("died"),
                FieldPanel("canonized"),
                FieldPanel("religious_order"),
                FieldPanel("burial_place"),
            ],
            heading="Identity",
        ),
        FieldPanel("patronage"),
        FieldPanel("significance"),
        FieldPanel("body"),
        FieldPanel("topics"),
        MultiFieldPanel(
            [
                FieldPanel("source_url"),
                FieldPanel("source_note"),
                FieldPanel("data_status"),
                FieldPanel("editor_notes"),
                FieldPanel("wikidata_id"),
                FieldPanel("portrait_url"),
                FieldPanel("portrait_credit"),
            ],
            heading="Editorial (internal)",
        ),
    ]


class SacredSitePage(RoutablePageMixin, Page):
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    canonical_status = models.CharField(max_length=60, blank=True, choices=CANONICAL_STATUS_CHOICES)
    locality = models.CharField(max_length=160, blank=True)
    country = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    date_display = models.CharField(max_length=160, blank=True)
    feast_day = models.CharField(max_length=120, blank=True)
    summary_short = models.TextField(blank=True)
    the_story = RichTextField(blank=True)
    church_recognition = RichTextField(blank=True)
    catholic_teaching = RichTextField(blank=True)
    pilgrimage_info = RichTextField(blank=True)
    go_deeper = RichTextField(blank=True)
    associated_saint = models.ForeignKey(
        "catalog.SaintPage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sites",
        help_text="The saint this site principally belongs to -- whose shrine or "
                  "tomb it is, or Our Lady for an apparition site.",
    )
    related_saints = ParentalManyToManyField(
        "catalog.SaintPage",
        blank=True,
        related_name="related_sites",
        help_text="Other saints connected to this site: the visionary of an "
                  "apparition, companions, or the figure a Holy Land place "
                  "belongs to. The principal saint goes in the field above.",
    )
    featured_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    topics = ParentalManyToManyField("catalog.Topic", blank=True, related_name="sites")
    location_link = models.URLField(blank=True)
    notes_internal = models.TextField(blank=True)

    # --- The Pilgrim's Quick Card ---------------------------------------
    # Six short facts above the collapsed travel panels. Most readers get
    # their answer here without opening anything. The sixth cell is the
    # existing feast_day field -- deliberately not duplicated.
    quick_ideal_stay = models.CharField(max_length=40, blank=True)
    quick_ideal_stay_note = models.CharField(max_length=60, blank=True)
    quick_best_months = models.CharField(max_length=40, blank=True)
    quick_best_months_note = models.CharField(max_length=60, blank=True)
    quick_airport = models.CharField(max_length=60, blank=True)
    quick_airport_note = models.CharField(max_length=60, blank=True)
    quick_language = models.CharField(max_length=60, blank=True)
    quick_language_note = models.CharField(max_length=60, blank=True)
    quick_accessibility = models.CharField(max_length=40, blank=True)
    quick_accessibility_note = models.CharField(max_length=60, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("featured_image"),
        MultiFieldPanel(
            [
                FieldPanel("category"),
                FieldPanel("canonical_status"),
                FieldPanel("locality"),
                FieldPanel("country"),
                FieldPanel("latitude"),
                FieldPanel("longitude"),
                FieldPanel("location_link"),
            ],
            heading="Location",
        ),
        MultiFieldPanel(
            [
                FieldPanel("date_display"),
                FieldPanel("feast_day"),
                FieldPanel("associated_saint"),
                FieldPanel("related_saints"),
                FieldPanel("topics"),
            ],
            heading="Identity",
        ),
        FieldPanel("summary_short"),
        FieldPanel("the_story"),
        FieldPanel("church_recognition"),
        FieldPanel("catholic_teaching"),
        MultiFieldPanel(
            [
                FieldPanel("quick_ideal_stay"),
                FieldPanel("quick_ideal_stay_note"),
                FieldPanel("quick_best_months"),
                FieldPanel("quick_best_months_note"),
                FieldPanel("quick_airport"),
                FieldPanel("quick_airport_note"),
                FieldPanel("quick_language"),
                FieldPanel("quick_language_note"),
                FieldPanel("quick_accessibility"),
                FieldPanel("quick_accessibility_note"),
            ],
            heading="The Pilgrim's Quick Card",
            classname="collapsed",
        ),
        InlinePanel("travel_sections", label="Plan Your Visit section"),
        FieldPanel("go_deeper"),
        FieldPanel("notes_internal"),
        MultiFieldPanel(
            [FieldPanel("pilgrimage_info")],
            heading="Visiting & Pilgrimage (legacy -- no longer displayed)",
            classname="collapsed",
        ),
    ]

    # (anchor id, rail label, field name) -- the narrative body of a site page,
    # in the order it is rendered. Adding a field here adds it to the rail.
    NARRATIVE_SECTIONS = [
        ("the-story", "The Story", "the_story"),
        ("church-recognition", "Church Recognition", "church_recognition"),
        ("catholic-teaching", "Catholic Teaching", "catholic_teaching"),
        # "visiting-pilgrimage" retired: its content moved into the
        # "Plan Your Visit" travel sections. pilgrimage_info is kept on the
        # model for one deploy so a rollback cannot lose text.
        ("go-deeper", "Go Deeper", "go_deeper"),
    ]

    @cached_property
    def narrative_sections(self):
        """Only the narrative fields the editor actually filled in."""
        return [
            {"anchor": anchor, "label": label, "body": getattr(self, field)}
            for anchor, label, field in self.NARRATIVE_SECTIONS
            if getattr(self, field)
        ]

    @property
    def has_location_section(self):
        return bool(self.location_link or (self.latitude and self.longitude))

    @cached_property
    def plan_clusters(self):
        """[(cluster label, [section, ...]), ...] -- filled sections only.

        Order comes from TRAVEL_CLUSTERS, not from the inline's sort_order, so
        every site page reads in the same shape. A cluster with nothing filled
        in renders nothing at all.
        """
        by_kind = {section.kind: section for section in self.travel_sections.all()}
        clusters = []
        number = 0
        for _, cluster_label, items in TRAVEL_CLUSTERS:
            rows = []
            for key, _ in items:
                section = by_kind.get(key)
                if section is None:
                    continue
                number += 1
                # Panels are numbered across the whole section, counting only
                # the ones that render, so a page with five of twelve reads
                # 1-5 rather than skipping numbers.
                section.display_number = number
                rows.append(section)
            if rows:
                clusters.append((cluster_label, rows))
        return clusters

    @cached_property
    def plan_sections(self):
        """The filled travel sections, flat, in canonical reading order."""
        return [section for _, rows in self.plan_clusters for section in rows]

    @property
    def has_plan_section(self):
        return bool(self.plan_clusters)

    @cached_property
    def quick_card_cells(self):
        """[(label, value, note), ...] for the cells the editor filled in."""
        candidates = [
            ("Ideal stay", self.quick_ideal_stay, self.quick_ideal_stay_note),
            ("Best months", self.quick_best_months, self.quick_best_months_note),
            ("Nearest airport", self.quick_airport, self.quick_airport_note),
            ("Language & currency", self.quick_language, self.quick_language_note),
            ("Feast day", self.feast_day, ""),
            ("Accessibility", self.quick_accessibility, self.quick_accessibility_note),
        ]
        return [(label, value, note) for label, value, note in candidates if value]

    @property
    def show_quick_card(self):
        """One fact is worse than none -- a half-empty card reads as broken."""
        return len(self.quick_card_cells) >= 2

    @cached_property
    def body_blocks(self):
        """The page body in render order: narrative sections and the plan block.

        The rail is derived from this same list, so the order a reader scrolls
        through and the order the rail lists can never drift apart. "Plan Your
        Visit" sits after Catholic Teaching and before Go Deeper -- you learn
        what the place is, then how to get there, then what to read next.
        """
        blocks = []
        for section in self.narrative_sections:
            blocks.append({"kind": "narrative", "section": section})
            if section["anchor"] == "catholic-teaching" and self.has_plan_section:
                blocks.append({"kind": "plan"})
        if self.has_plan_section and not any(b["kind"] == "plan" for b in blocks):
            blocks.append({"kind": "plan"})
        return blocks

    @property
    def section_nav(self):
        """Top-level rail entries. "Plan Your Visit" carries `children`.

        Children are a second rail level, NOT extra top-level entries: the
        `sections|length > 1` gate that decides whether the rail -- and with it
        the two-column grid -- renders at all counts this list only. Twelve
        children make the rail look full while the top-level count is still
        one, which is exactly how the saint pages collapsed in 22cee897.
        """
        items = []
        for block in self.body_blocks:
            if block["kind"] == "narrative":
                section = block["section"]
                items.append({"id": section["anchor"], "label": section["label"]})
            else:
                items.append(
                    {
                        "id": "plan-your-visit",
                        "label": "Plan Your Visit",
                        "children": [
                            {"id": s.kind, "label": TRAVEL_LABELS[s.kind]}
                            for s in self.plan_sections
                        ],
                    }
                )
        if self.has_location_section:
            items.append({"id": "location", "label": "Location"})
        return items

    @cached_property
    def trail_positions(self):
        """Where this site sits on any live trail that includes it.

        A site can belong to more than one trail (San Juan Capistrano is on the
        Mission Trail; a Serra route would claim it too), so this is a list, not
        a single value. Each entry carries the neighbours, which is what lets
        the site page offer "previous stop / next stop" without the reader
        having to go back out to the trail page.
        """
        positions = []
        for stop in self.trail_stops.all().select_related("trail"):
            trail = stop.trail
            if not trail.live:
                continue
            ordered = trail.ordered_stops
            try:
                index = [s.pk for s in ordered].index(stop.pk)
            except ValueError:  # pragma: no cover - stop vanished mid-request
                continue
            positions.append({
                "trail": trail,
                "stop": stop,
                "number": index + 1,
                "total": len(ordered),
                "previous": ordered[index - 1] if index > 0 else None,
                "next": ordered[index + 1] if index + 1 < len(ordered) else None,
            })
        positions.sort(key=lambda entry: entry["trail"].title)
        return positions

    def public_photos_queryset(self):
        """is_public_on_site=True, hidden_by_staff=False, newest share
        first — the gallery is nothing more than this query, at two
        different page sizes (preview strip vs. the full /gallery/ page)."""
        from pilgrims.models import PilgrimPhoto

        return (
            PilgrimPhoto.objects.filter(site=self, is_public_on_site=True, hidden_by_staff=False)
            .select_related("owner", "owner__pilgrim")
            .order_by("-public_shared_at")
        )

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["map_page"] = Page.objects.filter(slug=MAP_PAGE_SLUG).first()
        public_photos = self.public_photos_queryset()
        context["gallery_preview_photos"] = list(public_photos[:GALLERY_PREVIEW_COUNT])
        context["gallery_total_count"] = public_photos.count()
        return context

    @route(r"^gallery/$")
    def gallery_view(self, request):
        from django.http import Http404
        from django.shortcuts import render

        # Wagtail's own RoutablePageMixin.route() already refuses to reach
        # this view for an unpublished page (it checks self.live before
        # resolving any subroute) — this is a second, explicit check so
        # that guarantee doesn't depend on staying aware of that internal
        # behavior.
        if not self.live:
            raise Http404

        photos_qs = self.public_photos_queryset()
        paginator = Paginator(photos_qs, GALLERY_PAGE_SIZE)
        page_number = request.GET.get("page")
        try:
            photos_page = paginator.page(page_number)
        except PageNotAnInteger:
            photos_page = paginator.page(1)
        except EmptyPage:
            photos_page = paginator.page(paginator.num_pages) if paginator.num_pages else paginator.page(1)

        from pilgrims.models import PhotoReport

        return render(request, "catalog/sacred_site_gallery.html", {
            "page": self,
            "site_page": self,
            "photos_page": photos_page,
            "total_count": paginator.count,
            "report_reason_choices": PhotoReport.REASON_CHOICES,
        })


class SiteTravelSection(Orderable):
    """One panel of the "Plan Your Visit" section on a sacred site page.

    `kind` is a fixed choice rather than free text because it doubles as the
    URL anchor: /explore/.../lourdes/#where-to-stay. Free-text labels would be
    slugified, so a reworded heading would quietly break every shared and
    indexed deep link. The unique constraint is what guarantees one anchor
    cannot appear twice on a page.
    """

    page = ParentalKey(
        "catalog.SacredSitePage",
        related_name="travel_sections",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=40, choices=TRAVEL_SECTION_CHOICES)
    teaser = models.CharField(
        max_length=90,
        blank=True,
        help_text="One line under the heading, readable while the panel is closed.",
    )
    body = RichTextField()

    panels = [
        FieldPanel("kind"),
        FieldPanel("teaser"),
        FieldPanel("body"),
    ]

    class Meta(Orderable.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["page", "kind"],
                name="unique_travel_section_per_page",
            ),
        ]

    @property
    def label(self):
        return TRAVEL_LABELS.get(self.kind, self.kind)

    def __str__(self):
        return f"{self.page.title} - {self.label}"


class PilgrimageTrailPage(Page):
    """A route made of ordered stops -- the Camino, the Mission Trail.

    A trail is deliberately NOT a SacredSitePage with many coordinates. A site
    answers "what happened here"; a trail answers "in what order do I walk
    this", and its stops are a sequence whose order is the content. Modelling it
    as its own page type is what lets a stop be either a full site page or a
    bare waypoint, and lets the map draw a line rather than a cloud of pins.
    """

    trail_type = models.CharField(
        max_length=40,
        choices=TRAIL_TYPE_CHOICES,
        default="Walking route",
    )
    region = models.CharField(max_length=160, blank=True, help_text="e.g. Northern Spain")
    country = models.CharField(max_length=160, blank=True, help_text="e.g. France & Spain")
    start_point = models.CharField(max_length=160, blank=True)
    end_point = models.CharField(max_length=160, blank=True)

    length_display = models.CharField(
        max_length=80, blank=True, help_text='e.g. "490 miles / 790 km"'
    )
    duration_display = models.CharField(
        max_length=80, blank=True, help_text='e.g. "30-35 days on foot"'
    )
    best_season = models.CharField(max_length=80, blank=True)
    waymarking = models.CharField(
        max_length=80, blank=True, help_text='e.g. "Yellow arrows and scallop shells"'
    )

    summary_short = models.TextField(blank=True)
    the_story = RichTextField(blank=True)
    church_recognition = RichTextField(blank=True)
    catholic_teaching = RichTextField(blank=True)
    walking_the_route = RichTextField(blank=True)
    go_deeper = RichTextField(blank=True)

    featured_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    line_color = models.CharField(
        max_length=20,
        choices=TRAIL_COLOR_CHOICES,
        default=DEFAULT_TRAIL_COLOR,
        help_text="Color of this trail's line on the interactive map.",
    )
    topics = ParentalManyToManyField("catalog.Topic", blank=True, related_name="trails")
    official_url = models.URLField(blank=True)
    notes_internal = models.TextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("featured_image"),
        MultiFieldPanel(
            [
                FieldPanel("trail_type"),
                FieldPanel("region"),
                FieldPanel("country"),
                FieldPanel("start_point"),
                FieldPanel("end_point"),
                FieldPanel("official_url"),
                FieldPanel("line_color"),
            ],
            heading="The route",
        ),
        MultiFieldPanel(
            [
                FieldPanel("length_display"),
                FieldPanel("duration_display"),
                FieldPanel("best_season"),
                FieldPanel("waymarking"),
            ],
            heading="The Pilgrim's Quick Card",
        ),
        FieldPanel("summary_short"),
        FieldPanel("the_story"),
        FieldPanel("church_recognition"),
        FieldPanel("catholic_teaching"),
        FieldPanel("walking_the_route"),
        InlinePanel("stops", label="Stop", heading="Stops, in order along the route"),
        FieldPanel("go_deeper"),
        FieldPanel("topics"),
        FieldPanel("notes_internal"),
    ]

    class Meta:
        verbose_name = "Pilgrimage trail page"

    # Same shape as SacredSitePage.NARRATIVE_SECTIONS so the two page types
    # read alike and share includes/_section_nav.html unchanged.
    NARRATIVE_SECTIONS = [
        ("the-story", "The Story", "the_story"),
        ("church-recognition", "Church Recognition", "church_recognition"),
        ("catholic-teaching", "Catholic Teaching", "catholic_teaching"),
        ("walking-the-route", "Walking the Route", "walking_the_route"),
        ("go-deeper", "Go Deeper", "go_deeper"),
    ]

    @property
    def line_hex(self):
        return TRAIL_COLORS.get(self.line_color, TRAIL_COLORS[DEFAULT_TRAIL_COLOR])

    @cached_property
    def ordered_stops(self):
        """Every stop in route order, page-backed or not.

        This is the trail's content, so it is read once and cached: the stop
        list, the map payload, and each member site's "stop 7 of 21" band all
        derive from this one query.
        """
        return list(self.stops.all().select_related("site"))

    @cached_property
    def stops_for_display(self):
        """Stops numbered 1..n, in route order, ready for the template."""
        rows = []
        for index, stop in enumerate(self.ordered_stops, start=1):
            stop.stop_number = index
            rows.append(stop)
        return rows

    @cached_property
    def mapped_stops(self):
        """The stops that can actually be drawn -- the line is these, in order.

        A stop with no coordinates (a page still missing its lat/lng, a
        waypoint typed without one) is kept in the reading list but skipped
        here, so a half-filled stop shortens the line instead of dropping the
        map to a single point or throwing.
        """
        return [stop for stop in self.stops_for_display if stop.has_coordinates]

    @property
    def has_map(self):
        return len(self.mapped_stops) >= 2

    @cached_property
    def site_stops(self):
        """Stops that have their own site page."""
        return [stop for stop in self.stops_for_display if stop.site_id]

    @cached_property
    def quick_card_cells(self):
        """[(label, value), ...] for the cells the editor filled in."""
        duration_label = {
            "Walking route": "Time to walk",
            "Driving route": "Time to drive",
        }.get(self.trail_type, "Time needed")
        candidates = [
            ("Length", self.length_display),
            (duration_label, self.duration_display),
            ("Best season", self.best_season),
            ("Starts", self.start_point),
            ("Ends", self.end_point),
            ("Waymarking", self.waymarking),
        ]
        return [(label, value) for label, value in candidates if value]

    @property
    def show_quick_card(self):
        """One fact is worse than none -- same rule as the site pages."""
        return len(self.quick_card_cells) >= 2

    @cached_property
    def narrative_sections(self):
        return [
            {"anchor": anchor, "label": label, "body": getattr(self, field)}
            for anchor, label, field in self.NARRATIVE_SECTIONS
            if getattr(self, field)
        ]

    @cached_property
    def body_blocks(self):
        """Render order: the narrative, with the stop list before "Go Deeper".

        The reader learns what the road is, then walks down the list of places
        on it, then finds what to read next -- and because the rail is derived
        from this same list, scroll order and rail order cannot drift apart.
        """
        blocks = []
        stops_placed = False
        for section in self.narrative_sections:
            if section["anchor"] == "go-deeper" and self.stops_for_display and not stops_placed:
                blocks.append({"kind": "stops"})
                stops_placed = True
            blocks.append({"kind": "narrative", "section": section})
        if self.stops_for_display and not stops_placed:
            blocks.append({"kind": "stops"})
        return blocks

    @property
    def section_nav(self):
        items = []
        if self.has_map:
            items.append({"id": "the-route", "label": "The Route"})
        for block in self.body_blocks:
            if block["kind"] == "narrative":
                section = block["section"]
                items.append({"id": section["anchor"], "label": section["label"]})
            else:
                items.append({"id": "stops", "label": "Stops Along the Way"})
        return items

    def map_payload(self):
        """What the map JS needs to draw this trail. Also used by trails_json."""
        return {
            "slug": self.slug,
            "title": self.title,
            "url": self.url,
            "trail_type": self.trail_type,
            "color": self.line_hex,
            "length_display": self.length_display,
            "summary_short": self.summary_short,
            "stops": [
                {
                    "number": stop.stop_number,
                    "title": stop.display_title,
                    "locality": stop.display_locality,
                    "latitude": float(stop.latitude),
                    "longitude": float(stop.longitude),
                    "url": stop.url,
                    "note": stop.note,
                    "has_page": bool(stop.site_id),
                }
                for stop in self.mapped_stops
            ],
        }

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["map_page"] = Page.objects.filter(slug=MAP_PAGE_SLUG).first()
        return context


class TrailStop(Orderable):
    """One place on a trail, in route order.

    A stop is either a full site page or a bare waypoint. That split is the
    whole point: the Camino has to draw through Pamplona and Burgos long before
    either has a page written, and the Mission Trail wants every one of its
    twenty-one stops to BE a page. Promoting a waypoint later is one field
    change -- choose the page, and the typed name and coordinates stop being
    used, without the route ever breaking.
    """

    trail = ParentalKey(
        "catalog.PilgrimageTrailPage",
        related_name="stops",
        on_delete=models.CASCADE,
    )
    site = models.ForeignKey(
        "catalog.SacredSitePage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trail_stops",
        help_text="Choose the sacred site page for this stop, if it has one.",
    )
    waypoint_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Only for a stop with no page of its own yet. Ignored when a site page is chosen.",
    )
    waypoint_locality = models.CharField(max_length=160, blank=True)
    waypoint_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    waypoint_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    note = models.CharField(
        max_length=300,
        blank=True,
        help_text="One line on why this stop matters, shown in the stop list and map popup.",
    )
    distance_display = models.CharField(
        max_length=60,
        blank=True,
        help_text='e.g. "288 km from the start"',
    )

    panels = [
        FieldPanel("site"),
        MultiFieldPanel(
            [
                FieldPanel("waypoint_name"),
                FieldPanel("waypoint_locality"),
                FieldPanel("waypoint_latitude"),
                FieldPanel("waypoint_longitude"),
            ],
            heading="Waypoint (only if this stop has no page yet)",
            classname="collapsed",
        ),
        FieldPanel("note"),
        FieldPanel("distance_display"),
    ]

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if not self.site_id and not self.waypoint_name.strip():
            raise ValidationError(
                {"waypoint_name": "Choose a site page, or give this waypoint a name."}
            )

    @property
    def display_title(self):
        return self.site.title if self.site_id else self.waypoint_name

    @property
    def display_locality(self):
        if self.site_id:
            parts = [self.site.locality, self.site.country]
        else:
            parts = [self.waypoint_locality]
        return ", ".join(part for part in parts if part)

    @property
    def latitude(self):
        return self.site.latitude if self.site_id else self.waypoint_latitude

    @property
    def longitude(self):
        return self.site.longitude if self.site_id else self.waypoint_longitude

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def url(self):
        """The stop's own page, or nothing -- a waypoint is not a dead link."""
        if self.site_id and self.site.live:
            return self.site.url
        return ""

    def __str__(self):
        return f"{self.trail.title} - {self.display_title}"
