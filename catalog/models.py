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
