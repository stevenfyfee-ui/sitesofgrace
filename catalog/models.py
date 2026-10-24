import json
from datetime import date
from math import asin, cos, radians, sin, sqrt

from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils.functional import cached_property
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, ObjectList, TabbedInterface
from wagtail.contrib.routable_page.models import RoutablePageMixin, route
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from catalog.countries import COUNTRY_CHOICES, country_name
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

# Single source of truth for per-category colors. fill/stroke are the
# interactive map's pin colors; the map JS, its legend, the nearby cards and
# every other map read this dict through the {% category_styles_json %} tag
# (catalog/templatetags/category_styles.py) -- never a hard-coded copy. `dot`
# is the contrasting ink used on chips and hub tiles drawn in the fill color.
CATEGORY_STYLES = {
    "Marian Apparition":   {"fill": "#FFFFFF", "stroke": "#032553", "dot": "#032553"},
    "Eucharistic Miracle": {"fill": "#C79A42", "stroke": "#8A6A24", "dot": "#FDF9F2"},
    "Saints & Tombs":      {"fill": "#032553", "stroke": "#021A3B", "dot": "#C79A42"},
    "Holy Land":           {"fill": "#F3E4CE", "stroke": "#C79A42", "dot": "#C79A42"},
    "Shrine & Basilica":   {"fill": "#173A61", "stroke": "#0D2440", "dot": "#FDF9F2"},
}
DEFAULT_CATEGORY_STYLE = {"fill": "#173A61", "stroke": "#0D2440", "dot": "#FDF9F2"}

MAP_PAGE_SLUG = "interactive-map"

# "In the Area" — the band of nearby sites at the foot of a sacred site page.
# 40 miles is a same-day detour: close enough that a pilgrim already standing
# here can reasonably add it to the trip, far enough to catch the clusters
# (Rome, the Holy Land, the Mission corridor) that make a second stop obvious.
NEARBY_RADIUS_MILES = 40
NEARBY_MAX_RESULTS = 8
EARTH_RADIUS_MILES = 3958.8


def miles_between(lat1, lon1, lat2, lon2):
    """Great-circle distance in statute miles (haversine).

    Good to a fraction of a percent at these distances, and it needs no
    geospatial database extension -- the site runs on plain Postgres.
    """
    lat1, lon1, lat2, lon2 = map(radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))

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

# Plain-English badge text for each canonical_status. The stored (Latin)
# term is only ever shown as the badge's tooltip. A value missing from this
# map is shown as stored rather than guessed at.
CANONICAL_STATUS_LABELS = {
    "Constat de supernaturalitate (legacy)": "Church approved",
    "Recognized Devotion": "Church-recognized devotion",
    "Nihil obstat": "Devotion permitted",
    "Prae oculis habeatur": "Permitted, under observation",
    "Curatur": "Under the bishop's review",
    "Sub mandato": "Under Church supervision",
    "Prohibetur": "Not permitted",
    "Declaratio de non supernaturalitate": "Declared not supernatural",
}
# Values that mean "no judgment applies to this place" -- never a badge, chip or row.
STATUS_NOT_SHOWN = {"", "Not Applicable"}
APPROVED_STATUS = "Constat de supernaturalitate (legacy)"

# --- v2 site page choice fields (all optional; blank is always allowed) ---
EUCHARISTIC_KIND_CHOICES = [
    ("miracle", "Eucharistic miracle"),
    ("precious-blood", "Relic of the Precious Blood"),
    ("tradition", "Eucharistic tradition"),
]
VISIT_LENGTH_CHOICES = [
    ("half-day", "Half day"),
    ("one-day", "One day"),
    ("weekend", "Weekend (2–3 days)"),
    ("extended", "Extended (4+ days)"),
]
RESERVATION_CHOICES = [
    ("no", "No reservation needed"),
    ("yes", "Reservation required"),
    ("some", "Reservations for some activities"),
]
ACCESSIBILITY_LEVEL_CHOICES = [
    ("step-free", "Step-free main areas"),
    ("partly", "Partly accessible"),
    ("difficult", "Difficult access"),
    ("unknown", "Unknown"),
]
WORSHIP_STATUS_CHOICES = [
    ("active", "Active church with regular Mass"),
    ("occasional", "Mass occasionally"),
    ("no-regular", "No regular Mass"),
    ("not-catholic", "Not a Catholic church"),
]
GUIDE_LEVEL_CHOICES = [
    ("full", "Fully researched guide"),
    ("essential", "Essential visit guide"),
]

ACCOUNT_FEATURES = ["bold", "italic", "link"]
REFERENCE_FEATURES = ["link", "bold", "italic"]
READING_LIST_FEATURES = ["ul", "ol", "bold", "italic", "link"]

# Learn articles that explain how the Church judges these claims, by
# category; linked from "Information & sources" only while a live page has
# the slug. Other categories get no link.
CHURCH_JUDGMENT_LEARN = {
    "Marian Apparition": ("learn-mary-apparitions", "How the Church judges apparitions"),
    "Eucharistic Miracle": ("the-eucharist-and-eucharistic-miracles", "How the Church judges Eucharistic miracles"),
}


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

    search_fields = Page.search_fields + [
        index.SearchField("also_known_as", boost=3),
        index.AutocompleteField("also_known_as"),
        index.SearchField("honorific_type"),
        index.SearchField("feast_day"),
        index.SearchField("patronage", boost=2),
        index.AutocompleteField("patronage"),
        index.SearchField("significance"),
        index.SearchField("body"),
        index.SearchField("born"),
        index.SearchField("died"),
        index.SearchField("canonized"),
        index.RelatedFields("topics", [index.SearchField("name")]),
    ]

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

    search_fields = Page.search_fields + [
        index.SearchField("locality", boost=3),
        index.AutocompleteField("locality"),
        index.SearchField("country", boost=2),
        index.AutocompleteField("country"),
        index.SearchField("category"),
        index.SearchField("canonical_status"),
        index.SearchField("date_display"),
        index.SearchField("feast_day"),
        index.SearchField("summary_short", boost=2),
        index.AutocompleteField("summary_short"),
        index.SearchField("the_story"),
        index.SearchField("church_recognition"),
        index.SearchField("catholic_teaching"),
        index.SearchField("go_deeper"),
        index.RelatedFields("associated_saint", [index.SearchField("title")]),
        index.RelatedFields("related_saints", [index.SearchField("title")]),
        index.RelatedFields("topics", [index.SearchField("name")]),
        index.FilterField("category"),
    ]

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

    # --- Pilgrimage Platform v2 (rendered only behind SOG_V2_ENABLED) -----
    # Every field is optional and nullable; nothing here replaces an
    # existing field. The official website stays in location_link.
    country_code = models.CharField(
        max_length=2, null=True, blank=True, choices=COUNTRY_CHOICES,
        help_text="ISO 3166-1 code, set from propose_country_codes. The country text above is never changed.",
    )
    recognition_year = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Year of the Church\'s judgment. Shown as "Church approved · <year>".',
    )
    eucharistic_kind = models.CharField(
        max_length=20, null=True, blank=True, choices=EUCHARISTIC_KIND_CHOICES,
        help_text="Eucharistic pages only; shown as a chip beside the category.",
    )
    address = models.CharField(max_length=200, null=True, blank=True)
    time_needed = models.CharField(max_length=80, null=True, blank=True)
    visit_length = models.CharField(max_length=20, null=True, blank=True, choices=VISIT_LENGTH_CHOICES)
    admission = models.CharField(max_length=120, null=True, blank=True)
    reservation_required = models.CharField(
        max_length=10, null=True, blank=True, choices=RESERVATION_CHOICES,
    )
    accessibility_summary = models.CharField(max_length=160, null=True, blank=True)
    accessibility_level = models.CharField(
        max_length=20, null=True, blank=True, choices=ACCESSIBILITY_LEVEL_CHOICES,
    )
    worship_status = models.CharField(max_length=20, null=True, blank=True, choices=WORSHIP_STATUS_CHOICES)
    worship_note = models.CharField(max_length=160, null=True, blank=True)
    worship_schedule_url = models.URLField(null=True, blank=True)
    account_tradition = RichTextField(null=True, blank=True, features=ACCOUNT_FEATURES)
    account_church_judgment = RichTextField(null=True, blank=True, features=ACCOUNT_FEATURES)
    account_findings = RichTextField(null=True, blank=True, features=ACCOUNT_FEATURES)
    account_teaching = RichTextField(null=True, blank=True, features=ACCOUNT_FEATURES)
    guide_level = models.CharField(max_length=20, null=True, blank=True, choices=GUIDE_LEVEL_CHOICES)
    prep_prayer = RichTextField(null=True, blank=True, features=ACCOUNT_FEATURES)
    prep_readings = RichTextField(null=True, blank=True, features=READING_LIST_FEATURES)
    primary_references = RichTextField(null=True, blank=True, features=REFERENCE_FEATURES)
    # Internal only -- never rendered on the public page.
    reviewed_history_on = models.DateField(null=True, blank=True)
    reviewed_status_on = models.DateField(null=True, blank=True)
    reviewed_travel_on = models.DateField(null=True, blank=True)
    reviewed_contacts_on = models.DateField(null=True, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("featured_image"),
        MultiFieldPanel(
            [
                FieldPanel("category"),
                FieldPanel("eucharistic_kind"),
                FieldPanel("canonical_status"),
                FieldPanel("recognition_year"),
                FieldPanel("locality"),
                FieldPanel("country"),
                FieldPanel("country_code"),
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
        MultiFieldPanel(
            [
                FieldPanel("account_tradition"),
                FieldPanel("account_church_judgment"),
                FieldPanel("account_findings"),
                FieldPanel("account_teaching"),
            ],
            heading="How to read this account (shown when two or more are filled)",
            classname="collapsed",
        ),
        FieldPanel("catholic_teaching"),
        MultiFieldPanel(
            [
                FieldPanel("address"),
                FieldPanel("time_needed"),
                FieldPanel("visit_length"),
                FieldPanel("admission"),
                FieldPanel("reservation_required"),
                FieldPanel("accessibility_summary"),
                FieldPanel("accessibility_level"),
                FieldPanel("worship_status"),
                FieldPanel("worship_note"),
                FieldPanel("worship_schedule_url"),
            ],
            heading="At a Glance",
            classname="collapsed",
        ),
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
        FieldPanel("guide_level"),
        InlinePanel("travel_sections", label="Plan Your Visit section"),
        FieldPanel("go_deeper"),
        MultiFieldPanel(
            [FieldPanel("prep_prayer"), FieldPanel("prep_readings")],
            heading="Prepare spiritually",
            classname="collapsed",
        ),
        FieldPanel("primary_references"),
        MultiFieldPanel(
            [
                FieldPanel("reviewed_history_on"),
                FieldPanel("reviewed_status_on"),
                FieldPanel("reviewed_travel_on"),
                FieldPanel("reviewed_contacts_on"),
            ],
            heading="Verification (internal -- never shown publicly)",
            classname="collapsed",
        ),
        FieldPanel("notes_internal"),
        MultiFieldPanel(
            [FieldPanel("pilgrimage_info")],
            heading="Visiting & Pilgrimage (legacy -- no longer displayed)",
            classname="collapsed",
        ),
    ]

    # The default Content / Promote / Settings tabs, plus "Map & lodging"
    # for the v2 Where to Stay & Map section.
    edit_handler = TabbedInterface([
        ObjectList(content_panels, heading="Content"),
        ObjectList(
            [InlinePanel("map_points", label="Map point"), InlinePanel("lodgings", label="Place to stay")],
            heading="Map & lodging",
        ),
        ObjectList(Page.promote_panels, heading="Promote"),
        ObjectList(Page.settings_panels, heading="Settings"),
    ])

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

    # --- Church status (ALWAYS ON: both page versions use these) ---------

    @property
    def status_applies(self):
        """A status badge, chip or row renders only for a real judgment --
        never for blank or "Not Applicable". Gated on the value, not the
        category, so a Saints & Tombs page with an approved apparition keeps it."""
        return (self.canonical_status or "") not in STATUS_NOT_SHOWN

    @property
    def status_label(self):
        """Plain-English badge text; the stored term goes in the tooltip."""
        if not self.status_applies:
            return ""
        label = CANONICAL_STATUS_LABELS.get(self.canonical_status, self.canonical_status)
        if self.canonical_status == APPROVED_STATUS and self.recognition_year:
            label = f"{label} · {self.recognition_year}"
        return label

    # --- Pilgrimage Platform v2 page (only rendered behind the switch) ---

    @property
    def eucharistic_kind_label(self):
        if self.category != "Eucharistic Miracle" or not self.eucharistic_kind:
            return ""
        return self.get_eucharistic_kind_display()

    @cached_property
    def breadcrumbs(self):
        """Ancestors below the site's root page: Explore › Category."""
        site = self.get_site()
        root_depth = site.root_page.depth if site else 2
        return list(self.get_ancestors().live().filter(depth__gt=root_depth))

    @property
    def category_style(self):
        return CATEGORY_STYLES.get(self.category, DEFAULT_CATEGORY_STYLE)

    @property
    def country_display(self):
        """The approved code's name ("United Kingdom" for GB), else the text."""
        return country_name(self.country_code) or self.trip_readiness_country

    @property
    def location_line(self):
        return ", ".join(part for part in (self.locality, self.country) if part)

    @property
    def feast_line(self):
        if not self.feast_day:
            return ""
        return self.feast_day if self.feast_day.lower().startswith("feast") else f"Feast, {self.feast_day}"

    @property
    def directions_url(self):
        """Outbound Google Maps directions by coordinates -- a plain link, no API."""
        if self.latitude is None or self.longitude is None:
            return ""
        return f"https://www.google.com/maps/dir/?api=1&destination={self.latitude},{self.longitude}"

    @cached_property
    def at_a_glance_rows(self):
        """[{key, label, text, links: [(text, url, external)]}] for filled rows.

        Existing fields are reused before the v2 ones exist: Time needed
        falls back to the Quick Card's ideal stay, Accessibility to its
        accessibility cell. Review dates are never part of this.
        """
        rows = []

        def add(key, label, text, links=()):
            links = [link for link in links if link[1]]
            if text or links:
                rows.append({"key": key, "label": label, "text": text, "links": links})

        if self.address:
            add("address", "Address", self.address, [("Directions", self.directions_url, True)])
        if self.location_link:
            host = self.location_link.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")
            add("website", "Official website", "", [(host, self.location_link, True)])
        time_text = self.time_needed or self.get_visit_length_display() or self.quick_ideal_stay
        add("time", "Time needed", time_text)
        admission = " · ".join(
            part for part in (self.admission, self.get_reservation_required_display() if self.reservation_required else "") if part
        )
        add("admission", "Admission", admission)
        access = self.accessibility_summary or self.quick_accessibility
        if not access and self.accessibility_level and self.accessibility_level != "unknown":
            access = self.get_accessibility_level_display()
        add("accessibility", "Accessibility", access)
        if self.worship_status or self.worship_note:
            worship = " · ".join(
                part for part in (self.get_worship_status_display() if self.worship_status else "", self.worship_note) if part
            )
            add("worship", "Active place of worship", worship, [("Official schedule", self.worship_schedule_url, True)])
        if self.status_applies:
            add("recognition", "Church recognition", self.status_label)
        add("feast", "Feast day", self.feast_day)
        return rows

    @property
    def show_at_a_glance(self):
        return len(self.at_a_glance_rows) >= 2

    @cached_property
    def account_box_cells(self):
        """[(label, body)] for "How to read this account"; Marian apparition
        pages call the findings "Reported healings"."""
        findings = "Reported healings" if self.category == "Marian Apparition" else "Reported findings"
        cells = [
            ("The tradition", self.account_tradition),
            ("Church judgment", self.account_church_judgment),
            (findings, self.account_findings),
            ("Catholic teaching", self.account_teaching),
        ]
        return [(label, body) for label, body in cells if body]

    @property
    def show_account_box(self):
        return len(self.account_box_cells) >= 2

    @property
    def has_church_recognition_section(self):
        return bool(self.church_recognition) or self.show_account_box

    @property
    def v2_other_narrative(self):
        """Narrative sections the v2 layout doesn't name (Catholic Teaching,
        Go Deeper) -- kept, between Church Recognition and Plan Your Visit."""
        return [s for s in self.narrative_sections if s["anchor"] not in ("the-story", "church-recognition")]

    @property
    def has_prep_section(self):
        return bool(self.prep_prayer or self.prep_readings)

    @property
    def trip_readiness_country(self):
        """Country for the travel-advisory line, without import qualifiers
        like "Italy (tomb)" -- Phase 4 replaces this with country codes."""
        return (self.country or "").split(" (", 1)[0].strip()

    @property
    def overview_plan_target(self):
        """Where "Plan your own visit" goes: Where to Stay & Map, else the plan
        section, else the planner."""
        if self.has_stay_map_section:
            return "#stay-map"
        return "#plan-your-visit" if self.has_plan_section else f"/plan/?site={self.slug}"

    @cached_property
    def stay_map_points(self):
        return list(self.map_points.all())

    @cached_property
    def stay_lodgings(self):
        return list(self.lodgings.select_related("nearest_point"))

    @property
    def has_stay_map_section(self):
        """Shown with at least one place to stay or two map points."""
        return len(self.stay_lodgings) >= 1 or len(self.stay_map_points) >= 2

    @property
    def stay_has_affiliate(self):
        return any(lodging.is_affiliate_link for lodging in self.stay_lodgings)

    @property
    def stay_layers_present(self):
        """Layer keys with at least one item, so toggles for empty layers are left out."""
        layers = {point.layer for point in self.stay_map_points}
        if self.latitude is not None and self.longitude is not None:
            layers.add("shrine")
        if self.stay_lodgings:
            layers.add("lodging")
        return layers

    def stay_map_payload(self):
        """Everything site-map.js draws, for json_script. Coordinates as floats."""
        from django.urls import reverse

        def latlng(obj):
            return [float(obj.latitude), float(obj.longitude)]

        site = None
        if self.latitude is not None and self.longitude is not None:
            site = {"title": self.title, "latlng": latlng(self)}
        points = [
            {
                "name": p.name, "kind": p.kind, "kind_label": p.get_kind_display(), "layer": p.layer,
                "latlng": latlng(p), "note": p.note or "",
                "url": p.linked_page.url if p.linked_page_id and p.linked_page.live else "",
            }
            for p in self.stay_map_points
        ]
        lodgings = [
            {
                "id": lodging.pk, "n": index, "name": lodging.name, "latlng": latlng(lodging),
                "route": lodging.route_points, "summary": lodging.walk_summary,
                "book_url": (f"{reverse('go_lodging', args=[lodging.pk])}?from={self.pk}"
                             if lodging.outbound_url else ""),
                "rel": lodging.link_rel,
            }
            for index, lodging in enumerate(self.stay_lodgings, start=1)
        ]
        return {"site": site, "points": points, "lodgings": lodgings}

    @cached_property
    def connected_sites(self):
        """Up to 3 other live sites with the same principal saint that aren't
        already in nearby_sites, nearest first where both have coordinates."""
        if not self.associated_saint_id:
            return []
        listed = {entry["page"].pk for entry in self.nearby_sites}
        candidates = (
            SacredSitePage.objects.live()
            .filter(associated_saint_id=self.associated_saint_id)
            .exclude(pk=self.pk)
            .exclude(pk__in=listed)
        )
        found = []
        for site in candidates:
            miles = None
            if None not in (self.latitude, self.longitude, site.latitude, site.longitude):
                miles = miles_between(self.latitude, self.longitude, site.latitude, site.longitude)
            found.append({
                "page": site,
                "miles": miles,
                "miles_display": None if miles is None else ("<1" if miles < 1 else f"{int(round(miles)):,}"),
                "style": CATEGORY_STYLES.get(site.category, DEFAULT_CATEGORY_STYLE),
            })
        found.sort(key=lambda entry: (entry["miles"] is None, entry["miles"] or 0, entry["page"].title))
        return found[:3]

    @cached_property
    def guided_pilgrimages(self):
        """Live tours that stop here, soonest departure first (max 3)."""
        from tours.models import tours_for_site

        return tours_for_site(self)

    @property
    def v2_section_bar(self):
        """The sticky section bar: only sections that have content, in page order."""
        items = [{"id": "overview", "label": "Overview"}]
        if self.the_story:
            items.append({"id": "the-story", "label": "The Story"})
        if self.has_church_recognition_section:
            items.append({"id": "church-recognition", "label": "Church Recognition"})
        if self.has_plan_section:
            items.append({"id": "plan-your-visit", "label": "Plan Your Visit"})
        if self.has_stay_map_section:
            items.append({"id": "stay-map", "label": "Where to Stay & Map"})
        if self.guided_pilgrimages:
            items.append({"id": "guided-pilgrimages", "label": "Guided Pilgrimages"})
        if self.nearby_sites or self.connected_sites:
            items.append({"id": "nearby", "label": "Nearby Sacred Sites"})
        if self.has_prep_section:
            items.append({"id": "prepare", "label": "Prepare Spiritually"})
        items.append({"id": "pilgrim-photos", "label": "Pilgrim Photos"})
        return items

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

    @cached_property
    def nearby_sites(self):
        """Live sacred sites within NEARBY_RADIUS_MILES, nearest first.

        A cheap bounding box does the work in the database, then haversine
        trims the corners of that box down to a true circle. Sites with no
        coordinates simply never appear -- there is nothing to measure them
        against, and a "nearby" claim we cannot stand behind is worse than
        an absent one.
        """
        if self.latitude is None or self.longitude is None:
            return []

        lat = float(self.latitude)
        lon = float(self.longitude)
        lat_span = NEARBY_RADIUS_MILES / 69.0
        # Degrees of longitude shrink toward the poles; the floor keeps the box
        # from exploding near them (and from dividing by zero at 90 degrees).
        lon_span = NEARBY_RADIUS_MILES / max(69.0 * cos(radians(lat)), 1.0)

        candidates = (
            SacredSitePage.objects.live()
            .exclude(pk=self.pk)
            .filter(
                latitude__gte=lat - lat_span,
                latitude__lte=lat + lat_span,
                longitude__gte=lon - lon_span,
                longitude__lte=lon + lon_span,
            )
        )

        found = []
        for site in candidates:
            if site.latitude is None or site.longitude is None:
                continue
            distance = miles_between(lat, lon, site.latitude, site.longitude)
            if distance > NEARBY_RADIUS_MILES:
                continue
            found.append({
                "page": site,
                "miles": distance,
                "miles_display": "<1" if distance < 1 else str(int(round(distance))),
                "style": CATEGORY_STYLES.get(site.category, DEFAULT_CATEGORY_STYLE),
            })
        found.sort(key=lambda entry: entry["miles"])
        return found[:NEARBY_MAX_RESULTS]

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
        from core.v2 import v2_enabled

        if v2_enabled(request):
            if not self.guided_pilgrimages:
                from tours.models import TourInterest, tours_elsewhere

                from destinations.models import live_hubs_for_site
                from tours.models import tours_elsewhere_in_sites

                hubs = live_hubs_for_site(self)
                if hubs:
                    context["tours_elsewhere_label"] = hubs[0].title
                    context["tours_elsewhere"] = tours_elsewhere_in_sites(
                        self, [s.pk for s in hubs[0].sites if s.pk != self.pk])
                else:
                    context["tours_elsewhere_label"] = self.trip_readiness_country
                    context["tours_elsewhere"] = tours_elsewhere(self, self.trip_readiness_country)
                context["tour_interested"] = bool(
                    request.user.is_authenticated
                    and TourInterest.objects.filter(user=request.user, site=self).exists()
                )
            learn = CHURCH_JUDGMENT_LEARN.get(self.category)
            if learn and self.status_applies:
                context["church_judgment_learn_page"] = Page.objects.live().public().filter(slug=learn[0]).first()
                context["church_judgment_learn_text"] = learn[1]
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
    needs_confirmation = models.BooleanField(
        default=False,
        help_text='Shows a "Needs confirmation" pill on this panel (v2 page).',
    )

    panels = [
        FieldPanel("kind"),
        FieldPanel("teaser"),
        FieldPanel("body"),
        FieldPanel("needs_confirmation"),
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


# --- Map & lodging (v2 phase 3) --------------------------------------------

MAP_POINT_KIND_CHOICES = [
    ("main-entrance", "Main entrance"),
    ("accessible-entrance", "Accessible entrance"),
    ("sacred-place", "Sacred place"),
    ("prayer-location", "Prayer location"),
    ("train-station", "Train station"),
    ("bus-stop", "Bus / shuttle stop"),
    ("parking", "Parking"),
    ("other", "Other"),
]
ENTRANCE_KINDS = ("main-entrance", "accessible-entrance")
# Which map layer (toggle) each point kind belongs to.
MAP_POINT_LAYERS = {
    "main-entrance": "shrine", "accessible-entrance": "shrine",
    "sacred-place": "sacred", "prayer-location": "sacred", "other": "sacred",
    "train-station": "transit", "bus-stop": "transit", "parking": "transit",
}
LODGING_KIND_CHOICES = [
    ("hotel", "Hotel"),
    ("religious-house", "Religious house / guesthouse"),
    ("pilgrim", "Pilgrim accommodation"),
    ("hostel", "Hostel"),
]
SLOPE_CHOICES = [("level", "Level"), ("gentle", "Gentle slope"), ("steep", "Steep")]
STEP_FREE_CHOICES = [("yes", "Step-free route"), ("no", "Steps or steep sections"), ("unknown", "Step-free: unknown")]

LATITUDE_VALIDATORS = [MinValueValidator(-90), MaxValueValidator(90)]
LONGITUDE_VALIDATORS = [MinValueValidator(-180), MaxValueValidator(180)]


def parse_route_geojson(value):
    """[[lat, lng], ...] from a GeoJSON LineString (a geometry, or a Feature
    wrapping one), or raise ValidationError. GeoJSON order is [lng, lat]."""
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        raise ValidationError("Route must be valid JSON (a GeoJSON LineString).")
    if isinstance(data, dict) and data.get("type") == "Feature":
        data = data.get("geometry")
    if not isinstance(data, dict) or data.get("type") != "LineString":
        raise ValidationError('Route must be a GeoJSON LineString: {"type": "LineString", "coordinates": [...]}.')
    coords = data.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValidationError("A LineString needs at least two [longitude, latitude] positions.")
    points = []
    for position in coords:
        if (not isinstance(position, list) or len(position) < 2
                or not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in position[:2])):
            raise ValidationError("Every position must be [longitude, latitude] numbers.")
        lng, lat = position[0], position[1]
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise ValidationError(f"Position {position} is outside valid longitude/latitude ranges.")
        points.append([lat, lng])
    return points


class SiteMapPoint(Orderable):
    """A point on a site page's "Where to Stay & Map": entrances, sacred
    places, prayer locations and transit."""

    page = ParentalKey("catalog.SacredSitePage", on_delete=models.CASCADE, related_name="map_points")
    kind = models.CharField(max_length=30, choices=MAP_POINT_KIND_CHOICES)
    name = models.CharField(max_length=160)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=LATITUDE_VALIDATORS)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=LONGITUDE_VALIDATORS)
    note = models.CharField(max_length=160, null=True, blank=True)
    linked_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    verified = models.BooleanField(default=False)

    panels = [
        FieldPanel("kind"), FieldPanel("name"), FieldPanel("latitude"), FieldPanel("longitude"),
        FieldPanel("note"), FieldPanel("linked_page"), FieldPanel("verified"),
    ]

    @property
    def layer(self):
        return MAP_POINT_LAYERS.get(self.kind, "sacred")

    def __str__(self):
        return f"{self.page.title} – {self.name}" if self.page_id else self.name


class SiteLodging(Orderable):
    """A place to stay, with the hand-measured walk to the nearest entrance.
    No nightly prices: they go stale and imply a booking we don't make."""

    page = ParentalKey("catalog.SacredSitePage", on_delete=models.CASCADE, related_name="lodgings")
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=30, choices=LODGING_KIND_CHOICES)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=LATITUDE_VALIDATORS)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=LONGITUDE_VALIDATORS)
    website = models.URLField(max_length=500, null=True, blank=True)
    booking_url = models.URLField(max_length=500, null=True, blank=True)
    is_affiliate_link = models.BooleanField(default=False)
    nearest_point = models.ForeignKey(
        SiteMapPoint, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"kind__in": ENTRANCE_KINDS},
        help_text="The entrance the walk below is measured to (this page's entrances only).",
    )
    walk_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    walk_miles = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    slope = models.CharField(max_length=10, null=True, blank=True, choices=SLOPE_CHOICES)
    step_free = models.CharField(max_length=10, null=True, blank=True, choices=STEP_FREE_CHOICES)
    note = models.CharField(max_length=200, null=True, blank=True)
    route_geojson = models.TextField(
        null=True, blank=True,
        help_text="Verified walking route as a GeoJSON LineString ([longitude, latitude] pairs). "
                  "Leave blank until the route has been checked on foot.",
    )
    verified_on = models.DateField(null=True, blank=True, help_text="Admin only; never shown publicly.")

    panels = [
        FieldPanel("name"), FieldPanel("kind"), FieldPanel("latitude"), FieldPanel("longitude"),
        FieldPanel("website"), FieldPanel("booking_url"), FieldPanel("is_affiliate_link"),
        FieldPanel("nearest_point"), FieldPanel("walk_minutes"), FieldPanel("walk_miles"),
        FieldPanel("slope"), FieldPanel("step_free"), FieldPanel("note"),
        FieldPanel("route_geojson"), FieldPanel("verified_on"),
    ]

    def clean(self):
        super().clean()
        errors = {}
        if self.route_geojson and self.route_geojson.strip():
            try:
                parse_route_geojson(self.route_geojson)
            except ValidationError as exc:
                errors["route_geojson"] = exc.messages
        if self.nearest_point_id:
            point = self.nearest_point
            if point.kind not in ENTRANCE_KINDS:
                errors["nearest_point"] = ["Choose an entrance."]
            elif self.page_id and point.page_id != self.page_id:
                errors["nearest_point"] = ["Choose an entrance on this page."]
        if errors:
            raise ValidationError(errors)

    @property
    def route_points(self):
        """[[lat, lng], ...] or None. Only a route that parses is drawn."""
        if not self.route_geojson or not self.route_geojson.strip():
            return None
        try:
            return parse_route_geojson(self.route_geojson)
        except ValidationError:
            return None

    @property
    def outbound_url(self):
        return self.booking_url or self.website or ""

    @property
    def link_rel(self):
        return "sponsored nofollow noopener" if self.is_affiliate_link else "nofollow noopener"

    @property
    def walk_line(self):
        """'N min walk · X mi', or empty."""
        parts = []
        if self.walk_minutes:
            parts.append(f"{self.walk_minutes} min walk")
        if self.walk_miles is not None:
            parts.append(f"{self.walk_miles:f} mi")
        return " · ".join(parts)

    @property
    def walk_summary(self):
        """The info bar's sentence: 'Hotel A to Saint-Michel Gate: about 4
        minutes on foot, 0.2 mi. Level.'"""
        target = self.nearest_point.name if self.nearest_point_id else "the entrance"
        bits = []
        if self.walk_minutes:
            bits.append(f"about {self.walk_minutes} minutes on foot")
        if self.walk_miles is not None:
            bits.append(f"{self.walk_miles:f} mi")
        text = f"{self.name} to {target}" + (": " + ", ".join(bits) if bits else "") + "."
        if self.slope:
            text += f" {self.get_slope_display()}."
        return text

    def __str__(self):
        return self.name


class LodgingClickDaily(models.Model):
    """Outbound "Check availability" clicks per lodging, page and day -- the
    same pattern as tours.TourClickDaily: no IP, no user, no cookie."""

    lodging = models.ForeignKey(SiteLodging, on_delete=models.CASCADE, related_name="click_days")
    page = models.ForeignKey("wagtailcore.Page", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lodging", "page", "date"], name="unique_lodging_click_day"),
            models.UniqueConstraint(
                fields=["lodging", "date"], condition=models.Q(page__isnull=True),
                name="unique_lodging_click_day_no_page",
            ),
        ]

    @classmethod
    def record(cls, lodging, page=None, day=None):
        day = day or date.today()
        lookup = {"lodging": lodging, "page": page, "date": day}
        if cls.objects.filter(**lookup).update(count=models.F("count") + 1):
            return
        try:
            with transaction.atomic():
                cls.objects.create(count=1, **lookup)
        except IntegrityError:
            cls.objects.filter(**lookup).update(count=models.F("count") + 1)


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

    search_fields = Page.search_fields + [
        index.SearchField("trail_type"),
        index.SearchField("region", boost=2),
        index.AutocompleteField("region"),
        index.SearchField("country", boost=2),
        index.AutocompleteField("country"),
        index.SearchField("start_point"),
        index.SearchField("end_point"),
        index.SearchField("summary_short", boost=2),
        index.AutocompleteField("summary_short"),
        index.SearchField("the_story"),
        index.SearchField("church_recognition"),
        index.SearchField("catholic_teaching"),
        index.SearchField("walking_the_route"),
        index.SearchField("go_deeper"),
        index.RelatedFields("topics", [index.SearchField("name")]),
    ]

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
