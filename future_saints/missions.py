"""Future Saints Phase 3: the California Missions hub, the projects guide and
Build This Mission.

- MissionHubEntry: the 21 missions on the California Missions index, in
  founding order (seed_mission_hub fills them from the founding-order file).
  A pin's position always comes from the canonical page's latitude/longitude
  through future_saints.geo; the optional offsets only nudge its label.
- HubQuizQuestion / HubQuizChoice: the hub's "Test Your Knowledge" quiz.
- MissionProjectsGuidePage: the general "How to Build a California Mission
  Model" guide at /future-saints/california-missions/projects/.
- MissionSchoolProject: one Build This Mission project per mission learning
  page, with its own status. It shows only when its status is "published"
  (and its page is live). Publishing it needs a reference image with alt text
  (never a credit: credits are an internal note), 3+ steps, 1+ material,
  1+ source and the adult supervision notes.

No product names, brands, shopping links or prices anywhere (brief §7).
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.models import Orderable, Page
from wagtail.rich_text import expand_db_html

from .geo import VIEWBOX, VIEWBOX_HEIGHT, VIEWBOX_WIDTH, to_viewbox
from .models import CREDIT_HELP, FutureSaintsGateMixin

MISSION_COUNT = 21
OUTLINE_FILE = Path(__file__).resolve().parent / "data" / "california_outline.json"
PROJECT_STATUS_CHOICES = [
    ("not_started", "Not started"),
    ("draft", "Draft"),
    ("review_ready", "Ready for review"),
    ("published", "Published"),
]
PRINT_SHEETS = {"materials": "Materials Checklist", "steps": "Step-by-Step Instructions", "factcard": "Fact Card"}
PIN_RADIUS_PX = 24          # a tap within this many CSS pixels of 2+ pins opens the chooser

# Founding # badges: each sits up and to the right of its bell (CSS .fs-pin-num): its right
# edge BADGE_RIGHT px right of the pin's centre, its top BADGE_TOP px above it, BADGE_HEIGHT
# tall and 18 px wide (19.2 px for two digits). These offsets (CSS px, reviewed) move a
# badge so no two badges touch at any of the QA map widths; the pins never move.
# seed_mission_hub writes them into MissionHubEntry where no offset has been set.
BADGE_RIGHT, BADGE_TOP, BADGE_HEIGHT = 22, 21, 18
BADGE_OFFSETS = {
    1: (0, 8), 2: (0, 8), 3: (0, 12), 5: (8, 0), 7: (-12, 4), 8: (-36, 0), 9: (12, 0), 11: (-28, 0),
    13: (8, 0), 14: (12, -4), 15: (24, -8), 16: (12, -8), 17: (0, -20), 19: (-12, 0), 20: (0, -16), 21: (20, -4),
}
# The map's width in CSS px at the QA viewports 1440, 1024, 768, 430, 390, 360 (one viewBox
# unit = width/1000 px). Measured with tools/measure_mission_map.py.
MAP_WIDTHS_PX = {1440: 691.2, 1024: 546.0, 768: 706.6, 430: 395.6, 390: 358.0, 360: 328.0}


def badge_box(x, y, number, offset, scale):
    """A badge's box in CSS px, for a pin at viewBox (x, y) on a map `scale` px per unit."""
    cx, cy = x * scale, y * scale
    dx, dy = offset
    width = 19.2 if number >= 10 else 18
    return (cx + BADGE_RIGHT - width + dx, cy - BADGE_TOP + dy, cx + BADGE_RIGHT + dx, cy - BADGE_TOP + BADGE_HEIGHT + dy)


# City labels: parchment ribbons in the Pacific (viewBox units: x, y, width, height), each
# with a leader line to a dot at the city's real position (city-centre lat/lng through the
# same projection). The text is CITY_LABEL_FONT units, so it is at least 11 px only once the
# map is CITY_LABEL_MIN_MAP_PX wide; on a narrower map the ribbons, dots and leaders hide
# (a CSS container query on .fs-map). Placed so no ribbon touches the coast, an island, the
# compass, the scroll, another ribbon, or any bell or badge at the QA widths where they show.
CITY_LABEL_FONT = 22
CITY_LABEL_MIN_PX = 11
CITY_LABEL_MIN_MAP_PX = 1000 * CITY_LABEL_MIN_PX / CITY_LABEL_FONT      # 500 px
CITY_LABELS = [
    {"name": "San Francisco", "lines": ["San", "Francisco"], "lat": 37.7749, "lng": -122.4194, "box": (28, 472, 143, 54)},
    {"name": "Monterey", "lines": ["Monterey"], "lat": 36.6002, "lng": -121.8947, "box": (80, 576, 130, 32)},
    {"name": "Los Angeles", "lines": ["Los Angeles"], "lat": 34.0522, "lng": -118.2437, "box": (340, 860, 170, 32)},
    {"name": "San Diego", "lines": ["San Diego"], "lat": 32.7157, "lng": -117.1611, "box": (496, 996, 143, 32)},
]


# Steven's map art (static/future_saints/map-art/, built by tools/build_map_art.py): only the
# sailing ship and the whale, in open Pacific, as on the world map. (file, lat, lng, width in map
# units, height/width); a piece placed by map position instead uses lat=None and (x, y) in lng.
# Each is clear of every pin, badge, city label, leader line, the trail, the compass and the
# scroll at all six widths (test_maps_art_zoom). Decorative only, aria-hidden. The land pieces
# (mountains, trees, poppies) stay in map-art/ unused, in case they come back.
CALIFORNIA_ART = [
    ("sailing-ship.png", None, (60, 680), 90, 1.0),         # open Pacific
    ("whale-waves.png", 32.3, -120.3, 120, 0.6),            # open Pacific
]
CALIFORNIA_TEXTURE_TILE = 300      # map units per texture tile (1254 px), mirrored 2 x 2


PANEL_ART_SPEC = "fill-1600x900"          # the hub panel's picture (_art_frame.html, variant "feature")


def california_art():
    pieces = []
    for file, lat, where, width, aspect in CALIFORNIA_ART:
        cx, cy = where if lat is None else to_viewbox(lat, where)
        height = width * aspect
        pieces.append({"file": file, "x": round(cx - width / 2, 1), "y": round(cy - height / 2, 1), "w": width,
                       "h": round(height, 1)})
    return pieces


def city_labels():
    labels = []
    for city in CITY_LABELS:
        x, y, w, h = city["box"]
        dot_x, dot_y = to_viewbox(city["lat"], city["lng"])
        # The leader runs from the ribbon's nearest edge point to the dot.
        end_x, end_y = min(max(dot_x, x), x + w), min(max(dot_y, y), y + h)
        labels.append({
            "name": city["name"], "x": x, "y": y, "w": w, "h": h, "cx": x + w / 2,
            "lines": [{"text": t, "y": y + (h - 23 * (len(city["lines"]) - 1)) / 2 + 7.5 + 23 * i}
                      for i, t in enumerate(city["lines"])],
            "dot_x": round(dot_x, 2), "dot_y": round(dot_y, 2), "end_x": round(end_x, 2), "end_y": round(end_y, 2),
            "ribbon": (f"M{x + 6},{y} H{x + w - 6} L{x + w},{y + h / 2} L{x + w - 6},{y + h} "
                       f"H{x + 6} L{x},{y + h / 2} Z"),
        })
    return labels


def trail_points(entries):
    """The dotted trail through the pins, in the Mission Trail page's stop order."""
    from catalog.models import TrailStop

    from .learning import MISSION_TRAIL_SLUG

    placed = {e.canonical_id: e.canonical for e in entries
              if e.canonical.latitude is not None and e.canonical.longitude is not None}
    stops = TrailStop.objects.filter(trail__slug=MISSION_TRAIL_SLUG, site_id__in=placed).order_by("sort_order")
    points = [to_viewbox(placed[s.site_id].latitude, placed[s.site_id].longitude) for s in stops]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


@lru_cache(maxsize=1)
def california_outline():
    """{"path": ..., "rings": [...], "source": {...}} built by tools/build_california_outline.py."""
    return json.loads(OUTLINE_FILE.read_text(encoding="utf-8"))


def _image_field(help_text=""):
    return models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", help_text=help_text,
    )


def normalize_mission_name(text):
    """Words of a mission name for matching: accents, case, "Mission", "de", "la" and
    punctuation removed. "Mission San José" and "Mission San Jose" both give {"san", "jose"}."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z]+", plain)
    return [w for w in words if w not in {"mission", "de", "la"}]


def az_key(title):
    """A–Z order by the mission's own name: "Mission" and "Basilica" don't count; "La" does
    (La Purísima files under L). Accents and case are ignored."""
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return [w for w in re.findall(r"[a-z]+", plain) if w not in {"mission", "basilica"}]


# --- The hub ---------------------------------------------------------------------

class MissionHubEntry(Orderable):
    page = ParentalKey("future_saints.FutureSaintsIndexPage", related_name="mission_hub_entries", on_delete=models.CASCADE)
    canonical = models.ForeignKey(
        "catalog.SacredSitePage", on_delete=models.PROTECT, related_name="+",
        help_text="The Mission Trail page for this mission. Its latitude/longitude place the pin.",
    )
    founding_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(MISSION_COUNT)],
        help_text="Founding order 1–21 (not the trail's south-to-north order).",
    )
    founded_year = models.PositiveSmallIntegerField()
    founded_display = models.CharField(max_length=160, help_text="From the canonical page's founding text.")
    map_offset_x = models.FloatField(null=True, blank=True, help_text="Moves the Founding # badge only, in screen pixels. The pin never moves.")
    map_offset_y = models.FloatField(null=True, blank=True, help_text="Moves the Founding # badge only, in screen pixels. The pin never moves.")
    needs_review = models.BooleanField(
        default=False, help_text="Set while something on this mission (its date, its badge offset) needs checking. "
                                 "seed_mission_hub leaves a needs-review mission exactly as it is.",
    )
    review_note = models.CharField(max_length=255, blank=True, help_text="Internal review note only — never shown on the site.")

    panels = ["canonical", "founding_number", "founded_year", "founded_display", "map_offset_x", "map_offset_y",
              "needs_review", "review_note"]

    class Meta(Orderable.Meta):
        constraints = [
            models.UniqueConstraint(fields=["page", "founding_number"], name="fs_hub_unique_founding_number",
                                    deferrable=models.Deferrable.DEFERRED),
            models.UniqueConstraint(fields=["page", "canonical"], name="fs_hub_unique_canonical",
                                    deferrable=models.Deferrable.DEFERRED),
        ]

    def __str__(self):
        return f"#{self.founding_number} {self.canonical.title if self.canonical_id else ''}"


class HubQuizQuestion(ClusterableModel, Orderable):
    page = ParentalKey("future_saints.FutureSaintsIndexPage", related_name="hub_quiz_questions", on_delete=models.CASCADE)
    prompt = models.CharField(max_length=255)
    explanation = models.CharField(max_length=400, blank=True, help_text="Shown after any answer, kindly.")

    panels = [FieldPanel("prompt"), FieldPanel("explanation"), InlinePanel("choices", label="Choice", min_num=3, max_num=4)]


class HubQuizChoice(Orderable):
    question = ParentalKey(HubQuizQuestion, related_name="choices", on_delete=models.CASCADE)
    text = models.CharField(max_length=160)
    is_correct = models.BooleanField(default=False)

    panels = ["text", "is_correct"]


def hub_context(index, request):
    """Everything the California Missions hub template needs. Pins come from canonical lat/lng."""
    from .learning import MissionLearningPage, art_json

    entries = list(index.mission_hub_entries.select_related("canonical").order_by("founding_number"))
    stories = {
        p.canonical_id: p
        for p in MissionLearningPage.objects.child_of(index).live().public().select_related("canonical")
    }
    missions = []
    for entry in entries:
        site = entry.canonical
        placed = site.latitude is not None and site.longitude is not None
        x, y = to_viewbox(site.latitude, site.longitude) if placed else (None, None)
        story = stories.get(entry.canonical_id)
        project = story.published_project() if story else None
        missions.append({
            "number": entry.founding_number,
            "name": site.title,
            "slug": site.slug,
            "year": entry.founded_year,
            "founded": entry.founded_display,
            "lat": float(site.latitude) if placed else None,
            "x": x, "y": y,
            "left": f"{100 * x / VIEWBOX_WIDTH:.3f}" if placed else "",
            "top": f"{100 * y / VIEWBOX_HEIGHT:.3f}" if placed else "",
            "label_dx": entry.map_offset_x or 0, "label_dy": entry.map_offset_y or 0,
            "story": story,
            "story_url": story.get_url(request) if story else "",
            "subtitle": story.subtitle if story else "",
            "intro": story.intro if story else "",
            "project_url": (story.get_url(request) + "#build") if project else "",
            "art": story.card_art() if story else None,
        })
    wanted = request.GET.get("mission", "")
    selected = next((m for m in missions if m["slug"] == wanted), None) or (missions[0] if missions else None)
    for m in missions:
        m["selected"] = m is selected
    guide = MissionProjectsGuidePage.objects.child_of(index).live().public().first()
    panel_data = [
        {"slug": m["slug"], "number": m["number"], "name": m["name"], "founded": m["founded"],
         "subtitle": m["subtitle"], "intro": expand_db_html(m["intro"]) if m["intro"] else "", "story_url": m["story_url"],
         "project_url": m["project_url"], "art": art_json(m["art"], PANEL_ART_SPEC)}
        for m in missions
    ]
    return {
        "fs_missions": missions,
        "fs_selected": selected,
        "fs_missions_north_south": sorted([m for m in missions if m["lat"] is not None], key=lambda m: -m["lat"]),
        "fs_missions_az": sorted(missions, key=lambda m: az_key(m["name"])),
        "fs_stories": [m for m in missions if m["story"]],
        "fs_outline": california_outline(),
        "fs_viewbox": VIEWBOX,
        "fs_pin_radius": PIN_RADIUS_PX,
        "fs_city_labels": city_labels(),
        "fs_ca_art": california_art(),
        "fs_texture_tile": CALIFORNIA_TEXTURE_TILE,
        "fs_texture_tile2": CALIFORNIA_TEXTURE_TILE * 2,
        "fs_trail_points": trail_points(entries),
        "fs_panel_data": panel_data,
        "fs_quiz": index.hub_quiz_data(),
        "fs_guide_url": guide.get_url(request) if guide else "",
    }


# --- The general guide -------------------------------------------------------------

class MissionProjectsGuidePage(FutureSaintsGateMixin, Page):
    intro = models.TextField(blank=True, help_text="The guide's introduction.")
    supplies_note = models.TextField(blank=True, help_text='The note under the supplies list ("Always ask a grown-up …").')
    remember_people = models.TextField(blank=True, help_text='"Remember the people" text.')

    parent_page_types = ["future_saints.FutureSaintsIndexPage"]
    subpage_types = []
    max_count = 1

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        InlinePanel("plan_steps", label="Plan step", heading="Plan your project"),
        InlinePanel("supplies", label="Supply", heading="Supplies you may already have"),
        FieldPanel("supplies_note"),
        InlinePanel("safety_items", label="Safety item", heading="Safety first"),
        InlinePanel("build_steps", label="Build step", heading="Build a simple cardboard mission"),
        FieldPanel("remember_people"),
        InlinePanel("fact_card_labels", label="Fact card line", heading="Printable: My Mission Fact Card (lines to fill in)"),
        InlinePanel("checklist_items", label="Checklist item", heading="Printable: Project Checklist"),
    ]

    class Meta:
        verbose_name = "Future Saints mission projects guide"

    @classmethod
    def can_create_at(cls, parent):
        return super().can_create_at(parent) and getattr(parent.specific, "content_kind", None) == "california_mission"

    def get_template(self, request, *args, **kwargs):
        if request.GET.get("print") == "checklist":
            return "future_saints/print/guide_checklist.html"
        return "future_saints/mission_projects_guide_page.html"

    def get_context(self, request, *args, **kwargs):
        from .learning import MissionLearningPage

        context = super().get_context(request, *args, **kwargs)
        index = self.get_parent().specific
        stories = {p.canonical_id: p for p in MissionLearningPage.objects.child_of(index).live().public()}
        grid = []
        for entry in index.mission_hub_entries.select_related("canonical").order_by("founding_number"):
            story = stories.get(entry.canonical_id)
            project = story.published_project() if story else None
            grid.append({"number": entry.founding_number, "name": entry.canonical.title,
                         "url": (story.get_url(request) + "#build") if project else ""})
        context["fs_project_grid"] = grid
        return context


class _GuideItem(Orderable):
    class Meta(Orderable.Meta):
        abstract = True


class GuidePlanStep(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="plan_steps", on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=400, blank=True)
    panels = ["title", "text"]


class GuideSupply(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="supplies", on_delete=models.CASCADE)
    text = models.CharField(max_length=200)
    panels = ["text"]


class GuideSafetyItem(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="safety_items", on_delete=models.CASCADE)
    lead = models.CharField(max_length=60, blank=True, help_text='Bold words at the start, e.g. "Grown-ups only:".')
    text = models.CharField(max_length=200)
    panels = ["lead", "text"]


class GuideBuildStep(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="build_steps", on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=500, blank=True)
    panels = ["title", "text"]


class GuideFactCardLabel(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="fact_card_labels", on_delete=models.CASCADE)
    label = models.CharField(max_length=60)
    panels = ["label"]


class GuideChecklistItem(_GuideItem):
    page = ParentalKey(MissionProjectsGuidePage, related_name="checklist_items", on_delete=models.CASCADE)
    text = models.CharField(max_length=160)
    panels = ["text"]


# --- Build This Mission ---------------------------------------------------------------

class MissionSchoolProject(ClusterableModel):
    page = ParentalKey("future_saints.MissionLearningPage", related_name="school_projects", on_delete=models.CASCADE)
    project_title = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=PROJECT_STATUS_CHOICES, default="not_started",
                              help_text='Shown on the site only when "Published" (and the mission page is live).')
    grade_note = models.CharField(max_length=160, blank=True, help_text='"Good for" line.')
    difficulty = models.CharField(max_length=40, blank=True)
    stages_summary = models.CharField(max_length=255, blank=True, help_text="Hands-on stages, not times.")
    project_intro = models.TextField(blank=True)
    model_reference_image = _image_field("Required to publish: a picture of the mission as it looks today.")
    model_reference_image_alt = models.CharField(max_length=200, blank=True, help_text="Required to publish.")
    model_reference_image_credit = models.CharField(max_length=255, blank=True, help_text=CREDIT_HELP)
    historical_vs_restored_note = models.TextField(blank=True)
    finishing_tips = models.TextField(blank=True)
    adult_supervision_notes = models.TextField(blank=True, help_text="Required to publish.")
    last_reviewed_at = models.DateField(null=True, blank=True)

    panels = [
        FieldPanel("project_title"), FieldPanel("status"), FieldPanel("grade_note"), FieldPanel("difficulty"),
        FieldPanel("stages_summary"), FieldPanel("project_intro"),
        FieldPanel("model_reference_image"), FieldPanel("model_reference_image_alt"), FieldPanel("model_reference_image_credit"),
        FieldPanel("historical_vs_restored_note"),
        InlinePanel("features", label="Feature", heading="What makes this mission special"),
        InlinePanel("materials", label="Material", heading="Materials"),
        InlinePanel("steps", label="Step", heading="Steps (3 or more to publish)"),
        FieldPanel("finishing_tips"), FieldPanel("adult_supervision_notes"),
        InlinePanel("fact_card_rows", label="Fact card line", heading="Fact card"),
        InlinePanel("sources", label="Source", heading="Sources (1 or more to publish)"),
        FieldPanel("last_reviewed_at"),
    ]

    class Meta:
        verbose_name = "Build This Mission project"
        constraints = [models.UniqueConstraint(fields=["page"], name="fs_one_project_per_mission")]

    def __str__(self):
        return self.project_title

    @property
    def is_published(self):
        return self.status == "published"

    @property
    def reference_art(self):
        if self.model_reference_image is None:
            return None
        return {"image": self.model_reference_image, "alt": self.model_reference_image_alt or ""}


def project_publish_problems(*, image, alt, steps, materials, sources, adult_notes):
    """Why a project can't be published yet ([] when it can). Never asks for a credit."""
    problems = []
    if image is None:
        problems.append("Add a reference image of the mission.")
    if not (alt or "").strip():
        problems.append("Add alt text for the reference image.")
    if steps < 3:
        problems.append(f"Add at least 3 steps (it has {steps}).")
    if materials < 1:
        problems.append("Add at least 1 material.")
    if sources < 1:
        problems.append("Add at least 1 source.")
    if not (adult_notes or "").strip():
        problems.append("Fill in the adult supervision notes.")
    return problems


class ArchitecturalFeature(Orderable):
    project = ParentalKey(MissionSchoolProject, related_name="features", on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    text = models.CharField(max_length=400, blank=True)
    panels = ["title", "text"]


class ProjectMaterial(Orderable):
    project = ParentalKey(MissionSchoolProject, related_name="materials", on_delete=models.CASCADE)
    item = models.CharField(max_length=120)
    quantity = models.CharField(max_length=120, blank=True)
    alternative = models.CharField(max_length=160, blank=True, help_text="Or use instead.")
    safety_note = models.CharField(max_length=200, blank=True)
    panels = ["item", "quantity", "alternative", "safety_note"]


class ProjectStep(Orderable):
    project = ParentalKey(MissionSchoolProject, related_name="steps", on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    instructions = models.TextField()
    image = _image_field("Optional sketch or diagram.")
    image_alt = models.CharField(max_length=200, blank=True)
    safety_note = models.CharField(max_length=200, blank=True)
    panels = ["title", "instructions", "image", "image_alt", "safety_note"]

    @property
    def art(self):
        return {"image": self.image, "alt": self.image_alt or ""} if self.image_id else None


class ProjectFactCardRow(Orderable):
    project = ParentalKey(MissionSchoolProject, related_name="fact_card_rows", on_delete=models.CASCADE)
    label = models.CharField(max_length=60)
    value = models.CharField(max_length=200, blank=True)
    panels = ["label", "value"]


class ProjectSource(Orderable):
    project = ParentalKey(MissionSchoolProject, related_name="sources", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True)
    publisher = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True, help_text="What this source supports.")
    panels = ["title", "url", "publisher", "note"]


def check_project_forms(page_form):
    """Admin form: a project set to Published must meet the publishing rules (drafts can be incomplete)."""
    from .learning import _kept_forms

    ok = True
    for form in _kept_forms(page_form.formsets.get("school_projects")):
        data = form.cleaned_data
        if data.get("status") != "published":
            continue

        def count(name, required_field):
            return len([f for f in _kept_forms(form.formsets.get(name)) if f.cleaned_data.get(required_field)])

        problems = project_publish_problems(
            image=data.get("model_reference_image"), alt=data.get("model_reference_image_alt"),
            steps=count("steps", "title"), materials=count("materials", "item"), sources=count("sources", "title"),
            adult_notes=data.get("adult_supervision_notes"),
        )
        for problem in problems:
            form.add_error("status", problem)
            ok = False
    return ok


def validate_hub_entries(page_form):
    """Admin form: founding numbers 1–21 and each used once; each mission once."""
    from .learning import _kept_forms

    ok = True
    numbers, sites = {}, {}
    for form in _kept_forms(page_form.formsets.get("mission_hub_entries")):
        number = form.cleaned_data.get("founding_number")
        site = form.cleaned_data.get("canonical")
        if number in numbers:
            form.add_error("founding_number", f"Founding number {number} is used twice.")
            ok = False
        if site is not None and site.pk in sites:
            form.add_error("canonical", "This mission is listed twice.")
            ok = False
        numbers[number] = True
        if site is not None:
            sites[site.pk] = True
    return ok


__all__ = [
    "ArchitecturalFeature", "GuideBuildStep", "GuideChecklistItem", "GuideFactCardLabel", "GuidePlanStep",
    "GuideSafetyItem", "GuideSupply", "HubQuizChoice", "HubQuizQuestion", "MissionHubEntry",
    "MissionProjectsGuidePage", "MissionSchoolProject", "ProjectFactCardRow", "ProjectMaterial",
    "ProjectSource", "ProjectStep",
]
