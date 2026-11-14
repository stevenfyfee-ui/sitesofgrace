"""Future Saints: the children's learning section (Phase 1 -- shell, homepage, indexes).

Every page here is behind settings.SOG_FUTURE_SAINTS (future_saints.switch).
The pages never render a canonical page's travel, lodging, booking, pricing
or itinerary fields and never use the adult travel templates.

Pictures: a slot shows only an image uploaded to its own Future Saints field
(with its alt text); with none, the template draws the placeholder art frame.
Image credit fields are an internal note only and are never rendered on any
page, print sheet or meta. The adult site's images (e.g. SaintPage portraits,
CC-licensed and needing attribution) are never used here.
"""
import random
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from modelcluster.fields import ParentalKey
from django.http import Http404, JsonResponse
from django.template.response import TemplateResponse
from django.utils.cache import patch_cache_control
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, ObjectList, TabbedInterface
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.models import Orderable, Page

from home.legal import live_legal_urls

from .switch import future_saints_enabled, future_saints_public

ACCENT_CHOICES = [
    ("", "---------"),
    ("blue", "Blue"),
    ("sage", "Sage"),
    ("gold", "Gold"),
    ("terracotta", "Terracotta"),
    ("sand", "Sand"),
]

CONTENT_KIND_CHOICES = [
    ("", "---------"),
    ("saint", "Saints"),
    ("marian_apparition", "Marian apparitions"),
    ("eucharistic_miracle", "Eucharistic miracles"),
    ("holy_land", "Holy Land"),
    ("california_mission", "California missions"),
]

# Section navigation, in the order the header shows it (comp 03): UI labels,
# not editorial text, each with its sprite icon; each links to the live index
# of that kind.
NAV_KINDS = [
    ("saint", "Saints", "saint"),
    ("marian_apparition", "Marian Apparitions", "mary"),
    ("eucharistic_miracle", "Eucharistic Miracles", "miracle"),
    ("holy_land", "Holy Land", "holyland"),
    ("california_mission", "California Missions", "mission"),
]

# The line icon drawn on a subject card: from the linked index's subject,
# falling back to the card slot's usual subject while no index is linked.
KIND_ICONS = {
    "saint": "saint",
    "marian_apparition": "mary",
    "eucharistic_miracle": "miracle",
    "holy_land": "holyland",
    "california_mission": "mission",
}
SLOT_ICONS = {"card_1": "saint", "card_2": "mary", "card_3": "miracle", "card_4": "mission", "holy_land": "holyland"}


CREDIT_HELP = "Internal note only — never shown on the site."


def _credit_field():
    """An image credit: optional, kept in the admin as an internal record, never rendered."""
    return models.CharField(max_length=255, blank=True, help_text=CREDIT_HELP)


def _image_field(help_text=""):
    return models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", help_text=help_text,
    )


def _art(image, alt):
    """A picture the page shows, or None for the placeholder frame. Credits are never rendered."""
    if image is None:
        return None
    return {"image": image, "alt": alt or ""}


def _live_url(page, request):
    if page is None or not page.live:
        return ""
    return page.get_url(request)


class FutureSaintsGateMixin:
    """404 unless the switch allows this request; noindex, out of the
    sitemap and uncacheable by shared caches until the switch is "on"."""

    def serve(self, request, *args, **kwargs):
        # Admin previews come only from signed-in editors.
        if not getattr(request, "is_preview", False) and not future_saints_enabled(request):
            raise Http404
        response = super().serve(request, *args, **kwargs)
        if not future_saints_public():
            response["X-Robots-Tag"] = "noindex, nofollow"
            patch_cache_control(response, private=True, no_cache=True)
        return response

    def get_sitemap_urls(self, request=None):
        if not future_saints_public():
            return []
        return super().get_sitemap_urls(request)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        home = self.future_saints_home()
        context["fs_home"] = home
        context["fs_noindex"] = not future_saints_public()
        context["fs_nav"] = home.nav_items(request, self) if home else []
        world = home.world_map_page() if home else None
        context["fs_world_map_url"] = world.get_url(request) if world else ""
        context["fs_world_map_current"] = world is not None and world.pk == self.pk
        context["fs_search_url"] = home.search_url(request) if home else ""
        context["fs_privacy_url"] = live_legal_urls(request).get("privacy-policy", "")
        return context

    def future_saints_home(self):
        if isinstance(self, FutureSaintsHomePage):
            return self
        return FutureSaintsHomePage.objects.ancestor_of(self).first()


SAINT_OF_WEEK_TZ = ZoneInfo("America/Los_Angeles")


class FutureSaintsHomePageForm(WagtailAdminPageForm):
    """Saint of the Week schedule: each week_start is a Monday, and no two entries share one.
    Run in is_valid() so the inline rows are cleaned."""

    def is_valid(self):
        valid = super().is_valid()
        from .learning import _kept_forms

        ok, seen = True, set()
        for form in _kept_forms(self.formsets.get("saint_of_week_entries")):
            start = form.cleaned_data.get("week_start")
            if start is None:
                continue
            if start.weekday() != 0:
                form.add_error("week_start", f"{start:%A}, {start:%B} {start.day}, {start.year} isn't a Monday. "
                                             "Weeks start on Monday.")
                ok = False
            if start in seen:
                form.add_error("week_start", "Another entry already starts this week.")
                ok = False
            seen.add(start)
        return ok & valid


class FutureSaintsHomePage(FutureSaintsGateMixin, RoutablePageMixin, Page):
    eyebrow = models.CharField(max_length=80, blank=True, default="Sites of Grace | Future Saints")
    headline = models.CharField(max_length=120, blank=True, default="Explore the Wonders of Our Faith!")
    subheading = models.CharField(
        max_length=200, blank=True, default="Amazing stories, holy people, and places to discover.",
    )
    cta_label = models.CharField(max_length=40, blank=True, default="Start Exploring")
    hero_illustration = _image_field()
    hero_illustration_alt = models.CharField(max_length=200, blank=True)
    hero_illustration_credit = _credit_field()

    card_1_title = models.CharField(max_length=60, blank=True, default="Meet the Saints")
    card_1_line = models.CharField(max_length=120, blank=True)
    card_1_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_1_illustration = _image_field()
    card_1_illustration_alt = models.CharField(max_length=200, blank=True)
    card_1_illustration_credit = _credit_field()
    card_1_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="sage")

    card_2_title = models.CharField(max_length=60, blank=True, default="Mary & Apparitions")
    card_2_line = models.CharField(max_length=120, blank=True)
    card_2_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_2_illustration = _image_field()
    card_2_illustration_alt = models.CharField(max_length=200, blank=True)
    card_2_illustration_credit = _credit_field()
    card_2_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="blue")

    card_3_title = models.CharField(max_length=60, blank=True, default="Eucharistic Miracles")
    card_3_line = models.CharField(max_length=120, blank=True)
    card_3_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_3_illustration = _image_field()
    card_3_illustration_alt = models.CharField(max_length=200, blank=True)
    card_3_illustration_credit = _credit_field()
    card_3_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="gold")

    card_4_title = models.CharField(max_length=60, blank=True, default="California Missions")
    card_4_line = models.CharField(max_length=120, blank=True)
    card_4_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_4_illustration = _image_field()
    card_4_illustration_alt = models.CharField(max_length=200, blank=True)
    card_4_illustration_credit = _credit_field()
    card_4_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="terracotta")

    holy_land_title = models.CharField(max_length=60, blank=True, default="Explore the Holy Land")
    holy_land_line = models.CharField(max_length=160, blank=True)
    holy_land_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    holy_land_illustration = _image_field()
    holy_land_illustration_alt = models.CharField(max_length=200, blank=True)
    holy_land_illustration_credit = _credit_field()
    holy_land_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="sand")

    saint_of_week_heading = models.CharField(max_length=60, blank=True, default="Saint of the Week")
    # Phase 4: the scheduled entries (saint_of_week_entries) come first. This manual pick is the
    # fallback for a week with no entry; it links to that saint's published Future Saints page.
    saint_of_week = models.ForeignKey(
        "catalog.SaintPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True},
        help_text="Fallback for a week with no scheduled entry below. Links to this saint's published "
                  "Future Saints page (name only if there isn't one). Leave empty to hide the block then.",
    )
    saint_of_week_line = models.CharField(
        max_length=160, blank=True, help_text="One short line for children, shown under the name.",
    )

    church_status_note = models.CharField(
        max_length=255, blank=True,
        default="Church status information should be checked against official sources.",
        help_text="The Church-status line in the Future Saints footer, on every Future Saints page.",
    )
    quiz_page = models.ForeignKey(
        "future_saints.LearningPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True},
        help_text='The "Take a Quiz" block: a published story whose quiz to feature. Leave empty to pick '
                  "one published story with a quiz at random on each visit.",
    )

    parent_page_types = ["home.HomePage"]
    subpage_types = ["future_saints.FutureSaintsIndexPage", "future_saints.WorldMapPage"]
    max_count = 1
    base_form_class = FutureSaintsHomePageForm

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("eyebrow"),
                FieldPanel("headline"),
                FieldPanel("subheading"),
                FieldPanel("cta_label"),
                FieldPanel("hero_illustration"),
                FieldPanel("hero_illustration_alt"),
                FieldPanel("hero_illustration_credit"),
            ],
            heading="Hero",
        ),
    ] + [
        MultiFieldPanel(
            [
                FieldPanel(f"card_{n}_title"),
                FieldPanel(f"card_{n}_line"),
                FieldPanel(f"card_{n}_page"),
                FieldPanel(f"card_{n}_illustration"),
                FieldPanel(f"card_{n}_illustration_alt"),
                FieldPanel(f"card_{n}_illustration_credit"),
                FieldPanel(f"card_{n}_accent"),
            ],
            heading=f"Subject card {n}",
        )
        for n in (1, 2, 3, 4)
    ] + [
        MultiFieldPanel(
            [
                FieldPanel("holy_land_title"),
                FieldPanel("holy_land_line"),
                FieldPanel("holy_land_page"),
                FieldPanel("holy_land_illustration"),
                FieldPanel("holy_land_illustration_alt"),
                FieldPanel("holy_land_illustration_credit"),
                FieldPanel("holy_land_accent"),
            ],
            heading="Holy Land feature card (full width, below the four cards)",
        ),
        MultiFieldPanel(
            [FieldPanel("saint_of_week_heading"), FieldPanel("saint_of_week"), FieldPanel("saint_of_week_line")],
            heading="Saint of the Week: fallback pick (for a week with no scheduled entry)",
        ),
        InlinePanel("saint_of_week_entries", label="Week", heading="Saint of the Week: schedule (weeks start on Monday)"),
        FieldPanel("quiz_page"),
        FieldPanel("church_status_note"),
    ]

    class Meta:
        verbose_name = "Future Saints home page"

    def nav_items(self, request, current):
        """[{label, icon, url, current}] for the five subject indexes that are live."""
        indexes = {
            p.content_kind: p
            for p in FutureSaintsIndexPage.objects.child_of(self).live().order_by("path")
        }
        items = []
        for kind, label, icon in NAV_KINDS:
            page = indexes.get(kind)
            if page is None:
                continue
            if current.pk == page.pk:
                aria_current = "page"
            elif current.path.startswith(page.path):
                aria_current = "true"
            else:
                aria_current = ""
            items.append({"label": label, "icon": icon, "url": page.get_url(request), "current": aria_current})
        return items

    @property
    def hero_art(self):
        return _art(self.hero_illustration, self.hero_illustration_alt)

    def _card(self, prefix, request):
        page = getattr(self, f"{prefix}_page")
        return {
            "title": getattr(self, f"{prefix}_title"),
            "line": getattr(self, f"{prefix}_line"),
            "page": page,
            "url": _live_url(page, request),
            "icon": KIND_ICONS.get(page.content_kind, SLOT_ICONS[prefix]) if page else SLOT_ICONS[prefix],
            "accent": getattr(self, f"{prefix}_accent"),
            "art": _art(getattr(self, f"{prefix}_illustration"), getattr(self, f"{prefix}_illustration_alt")),
            "slot": prefix.replace("_", " "),
        }

    def world_map_page(self):
        from .worldmap import WorldMapPage

        return WorldMapPage.objects.child_of(self).live().public().first()

    def saint_of_week_card(self, request, today=None):
        """The scheduled entry whose week (Monday to Sunday, America/Los_Angeles) contains today;
        otherwise the fallback pick; otherwise None (the block is hidden). It links to the
        Future Saints saint page, never the adult SaintPage, and uses no adult picture."""
        from .learning import SaintLearningPage

        today = today or timezone.now().astimezone(SAINT_OF_WEEK_TZ).date()
        monday = today - timedelta(days=today.weekday())
        entry = next((e for e in self.saint_of_week_entries.all()
                      if e.week_start == monday and e.saint_id and e.saint.live), None)
        if entry is not None:
            page = entry.saint
            return {"name": page.student_title or page.title, "line": entry.line, "url": page.get_url(request),
                    "art": page.art()["thumbnail"], "scheduled": True}
        saint = self.saint_of_week
        if saint is None or not saint.live:
            return None
        page = SaintLearningPage.objects.live().public().filter(canonical=saint).first()
        return {"name": (page.student_title or page.title) if page else saint.title, "line": self.saint_of_week_line,
                "url": page.get_url(request) if page else "", "art": page.art()["thumbnail"] if page else None,
                "scheduled": False}

    def quiz_card(self, request):
        """The featured story's quiz, or one published story with a quiz chosen per request."""
        from .learning import LearningPage

        page = self.quiz_page.specific if self.quiz_page_id and self.quiz_page.live else None
        if page is None or not page.quiz_questions.exists():
            pool = list(LearningPage.objects.descendant_of(self).live().public()
                        .filter(quiz_questions__isnull=False).distinct().specific())
            page = random.choice(pool) if pool else None
        if page is None:
            return None
        return {"title": page.student_title or page.title, "url": page.get_url(request) + "#quiz"}

    # --- Search (future_saints.search): published Future Saints pages only, nothing stored ---
    def search_url(self, request=None):
        return self.get_url(request) + self.reverse_subpage("search_results")

    @path("search/", name="search_results")
    def search_results(self, request):
        """The no-JavaScript results page (and where Enter goes): grouped cards, always noindex."""
        from .search import grouped, search, search_index, suggestions

        query = " ".join(request.GET.get("q", "").split())[:100]
        index = search_index(self)
        results = search(index, query)
        context = FutureSaintsGateMixin.get_context(self, request)
        context.update({"fs_search_page": True, "fs_noindex": True, "fs_search_query": query,
                        "fs_search_groups": grouped(results), "fs_search_count": len(results),
                        "fs_search_suggestions": suggestions(index) if query and not results else []})
        response = TemplateResponse(request, "future_saints/search_page.html", context)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @path("search/index/", name="search_index")
    def search_index_json(self, request):
        """The type-ahead's index: the browser fetches it once and filters it locally."""
        from .search import GROUPS, search_index

        response = JsonResponse({"groups": GROUPS, "entries": search_index(self)})
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def get_context(self, request, *args, **kwargs):
        from .worldmap import world_preview

        context = super().get_context(request, *args, **kwargs)
        cards = [self._card(f"card_{n}", request) for n in (1, 2, 3, 4)]
        holy_land = self._card("holy_land", request)
        context["fs_cards"] = cards
        context["fs_holy_land"] = holy_land
        context["fs_saint"] = self.saint_of_week_card(request)
        context["fs_quiz_card"] = self.quiz_card(request)
        context["fs_world_preview"] = world_preview(self, request)
        return context


class SaintOfWeekEntry(Orderable):
    page = ParentalKey(FutureSaintsHomePage, related_name="saint_of_week_entries", on_delete=models.CASCADE)
    week_start = models.DateField(help_text="The Monday the week starts (America/Los_Angeles).")
    saint = models.ForeignKey(
        "future_saints.SaintLearningPage", on_delete=models.CASCADE, related_name="+",
        limit_choices_to={"live": True}, help_text="A published Future Saints saint page.",
    )
    line = models.CharField(max_length=160, blank=True, help_text="One short line for children, under the name.")

    panels = ["week_start", "saint", "line"]

    class Meta(Orderable.Meta):
        ordering = ["week_start"]


class FutureSaintsIndexPageForm(WagtailAdminPageForm):
    """The California Missions hub's rules: founding numbers 1–21 used once, each
    mission once, and the hub quiz's 3–4 choices with one correct (five to publish,
    once it has questions). Run in is_valid() so the inline rows are cleaned."""

    def is_valid(self):
        from .learning import check_quiz
        from .missions import validate_hub_entries

        valid = super().is_valid()
        return check_quiz(self, "hub_quiz_questions", "The hub quiz", required=False) & validate_hub_entries(self) & valid


class FutureSaintsIndexPage(FutureSaintsGateMixin, Page):
    content_kind = models.CharField(max_length=30, blank=True, choices=CONTENT_KIND_CHOICES)
    intro = models.TextField(max_length=400, blank=True, help_text="One or two short sentences for children.")
    accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES)
    banner_illustration = _image_field()
    banner_illustration_alt = models.CharField(max_length=200, blank=True)
    banner_illustration_credit = _credit_field()

    # The California Missions hub (Phase 3): used only on the california_mission index.
    hub_eyebrow = models.CharField(max_length=80, blank=True)
    hub_title = models.CharField(max_length=120, blank=True, help_text="Leave empty to use the page title.")
    hub_subtitle = models.CharField(max_length=255, blank=True)
    hub_intro = models.TextField(max_length=800, blank=True, help_text="The intro under the map.")
    map_note = models.CharField(max_length=300, blank=True, help_text="Small print under the map.")
    timeline_heading = models.CharField(max_length=120, blank=True, help_text='e.g. "The Missions in Founding Order".')
    native_peoples_text = models.TextField(max_length=2000, blank=True, help_text="The hub's Native Peoples section.")
    projects_banner_heading = models.CharField(max_length=120, blank=True)
    projects_banner_text = models.CharField(max_length=255, blank=True)
    projects_banner_button = models.CharField(max_length=60, blank=True)

    parent_page_types = ["future_saints.FutureSaintsHomePage"]
    # Each index takes only the learning type matching its content_kind;
    # LearningPage.can_create_at() narrows this list per index.
    subpage_types = [
        "future_saints.SaintLearningPage",
        "future_saints.MarianLearningPage",
        "future_saints.EucharisticLearningPage",
        "future_saints.HolyLandLearningPage",
        "future_saints.MissionLearningPage",
        "future_saints.MissionProjectsGuidePage",
    ]
    base_form_class = FutureSaintsIndexPageForm

    content_panels = Page.content_panels + [
        FieldPanel("content_kind"),
        FieldPanel("intro"),
        FieldPanel("accent"),
        MultiFieldPanel(
            [
                FieldPanel("banner_illustration"),
                FieldPanel("banner_illustration_alt"),
                FieldPanel("banner_illustration_credit"),
            ],
            heading="Banner illustration",
        ),
    ]
    hub_panels = [
        MultiFieldPanel(
            [FieldPanel("hub_eyebrow"), FieldPanel("hub_title"), FieldPanel("hub_subtitle"), FieldPanel("hub_intro"),
             FieldPanel("map_note")],
            heading="Hub title, intro and map note",
        ),
        MultiFieldPanel([FieldPanel("timeline_heading"), FieldPanel("native_peoples_text")], heading="Hub sections"),
        MultiFieldPanel(
            [FieldPanel("projects_banner_heading"), FieldPanel("projects_banner_text"), FieldPanel("projects_banner_button")],
            heading="Mission School Projects banner",
        ),
        InlinePanel("mission_hub_entries", label="Mission", heading="The 21 missions (founding order)"),
        InlinePanel("hub_quiz_questions", label="Quiz question", heading="Hub quiz: Test Your Knowledge (five questions)"),
    ]
    edit_handler = TabbedInterface([
        ObjectList(content_panels, heading="Content"),
        ObjectList(hub_panels, heading="Missions hub (California Missions only)"),
        ObjectList(Page.promote_panels, heading="Promote"),
        ObjectList(Page.settings_panels, heading="Settings"),
    ])

    class Meta:
        verbose_name = "Future Saints subject index"

    def clean(self):
        super().clean()
        if not self.content_kind:
            return
        parent = self.get_parent() if self.pk else None
        if parent is None:
            return
        clash = FutureSaintsIndexPage.objects.child_of(parent).filter(content_kind=self.content_kind)
        if clash.exclude(pk=self.pk).exists():
            raise ValidationError({"content_kind": "There is already an index for this subject."})

    @property
    def banner_art(self):
        return _art(self.banner_illustration, self.banner_illustration_alt)

    @property
    def is_missions_hub(self):
        return self.content_kind == "california_mission"

    def hub_quiz_data(self):
        data = []
        for question in self.hub_quiz_questions.all():
            choices = [{"text": c.text, "correct": c.is_correct} for c in question.choices.all() if c.text]
            if question.prompt and choices:
                data.append({"prompt": question.prompt, "explanation": question.explanation, "choices": choices})
        return data

    def get_template(self, request, *args, **kwargs):
        if self.is_missions_hub:
            return "future_saints/missions_hub_page.html"
        return super().get_template(request, *args, **kwargs)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["fs_children"] = [p.specific for p in self.get_children().live().public().order_by("path")]
        context["fs_type_icon"] = KIND_ICONS.get(self.content_kind, "mark")
        if self.is_missions_hub:
            from .missions import hub_context

            context.update(hub_context(self, request))
        return context


# Phase 2: the five learning page types live in their own module.
from .learning import (  # noqa: E402,F401
    BibleReference,
    EucharisticLearningPage,
    FunFact,
    HolyLandLearningPage,
    LearningPage,
    MarianLearningPage,
    MissionLearningPage,
    QuickFact,
    QuizChoice,
    QuizQuestion,
    SaintLearningPage,
    SourceLink,
    TimelineEntry,
    WordToKnow,
)

# Phase 3: the California Missions hub, the projects guide and Build This Mission.
from .missions import (  # noqa: E402,F401
    ArchitecturalFeature,
    GuideBuildStep,
    GuideChecklistItem,
    GuideFactCardLabel,
    GuidePlanStep,
    GuideSafetyItem,
    GuideSupply,
    HubQuizChoice,
    HubQuizQuestion,
    MissionHubEntry,
    MissionProjectsGuidePage,
    MissionSchoolProject,
    ProjectFactCardRow,
    ProjectMaterial,
    ProjectSource,
    ProjectStep,
)

# Phase 4: the World Discovery Map.
from .worldmap import WorldMapPage  # noqa: E402,F401
