"""Future Saints: the children's learning section (Phase 1 -- shell, homepage, indexes).

Every page here is behind settings.SOG_FUTURE_SAINTS (future_saints.switch).
The pages never render a canonical page's travel, lodging, booking, pricing
or itinerary fields and never use the adult travel templates.

Pictures: a slot shows its image only when the image AND its credit are
filled. A saint's existing portrait is used only when portrait_credit is
filled. Otherwise the template draws the placeholder art frame -- there is no
fallback to an uncredited canonical image.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.http import Http404
from django.utils.cache import patch_cache_control
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.models import Page

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


def _image_field(help_text=""):
    return models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", help_text=help_text,
    )


def _art(image, alt, credit):
    """A picture the page may show, or None for the placeholder frame."""
    if image is None or not (credit or "").strip():
        return None
    return {"image": image, "alt": alt or "", "credit": credit.strip()}


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
        context["fs_privacy_url"] = live_legal_urls(request).get("privacy-policy", "")
        return context

    def future_saints_home(self):
        if isinstance(self, FutureSaintsHomePage):
            return self
        return FutureSaintsHomePage.objects.ancestor_of(self).first()


class FutureSaintsHomePage(FutureSaintsGateMixin, Page):
    eyebrow = models.CharField(max_length=80, blank=True, default="Sites of Grace | Future Saints")
    headline = models.CharField(max_length=120, blank=True, default="Explore the Wonders of Our Faith!")
    subheading = models.CharField(
        max_length=200, blank=True, default="Amazing stories, holy people, and places to discover.",
    )
    cta_label = models.CharField(max_length=40, blank=True, default="Start Exploring")
    hero_illustration = _image_field("Shown only when the credit below is filled.")
    hero_illustration_alt = models.CharField(max_length=200, blank=True)
    hero_illustration_credit = models.CharField(max_length=255, blank=True)

    card_1_title = models.CharField(max_length=60, blank=True, default="Meet the Saints")
    card_1_line = models.CharField(max_length=120, blank=True)
    card_1_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_1_illustration = _image_field("Shown only when the credit below is filled.")
    card_1_illustration_alt = models.CharField(max_length=200, blank=True)
    card_1_illustration_credit = models.CharField(max_length=255, blank=True)
    card_1_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="sage")

    card_2_title = models.CharField(max_length=60, blank=True, default="Mary & Apparitions")
    card_2_line = models.CharField(max_length=120, blank=True)
    card_2_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_2_illustration = _image_field("Shown only when the credit below is filled.")
    card_2_illustration_alt = models.CharField(max_length=200, blank=True)
    card_2_illustration_credit = models.CharField(max_length=255, blank=True)
    card_2_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="blue")

    card_3_title = models.CharField(max_length=60, blank=True, default="Eucharistic Miracles")
    card_3_line = models.CharField(max_length=120, blank=True)
    card_3_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_3_illustration = _image_field("Shown only when the credit below is filled.")
    card_3_illustration_alt = models.CharField(max_length=200, blank=True)
    card_3_illustration_credit = models.CharField(max_length=255, blank=True)
    card_3_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="gold")

    card_4_title = models.CharField(max_length=60, blank=True, default="California Missions")
    card_4_line = models.CharField(max_length=120, blank=True)
    card_4_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    card_4_illustration = _image_field("Shown only when the credit below is filled.")
    card_4_illustration_alt = models.CharField(max_length=200, blank=True)
    card_4_illustration_credit = models.CharField(max_length=255, blank=True)
    card_4_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="terracotta")

    holy_land_title = models.CharField(max_length=60, blank=True, default="Explore the Holy Land")
    holy_land_line = models.CharField(max_length=160, blank=True)
    holy_land_page = models.ForeignKey(
        "future_saints.FutureSaintsIndexPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    holy_land_illustration = _image_field("Shown only when the credit below is filled.")
    holy_land_illustration_alt = models.CharField(max_length=200, blank=True)
    holy_land_illustration_credit = models.CharField(max_length=255, blank=True)
    holy_land_accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES, default="sand")

    # Unused since Phase 2a (one reading level, no "Choose Your Adventure"
    # block). The columns stay because migration 0001 is already applied in
    # production and standing rule 4 forbids removing fields without approval.
    adventure_heading = models.CharField(max_length=80, blank=True, default="Choose Your Adventure!")
    adventure_text = models.CharField(
        max_length=200, blank=True,
        default="Pick your reading level so we can show you the right amount of information.",
    )

    saint_of_week_heading = models.CharField(max_length=60, blank=True, default="Saint of the Week")
    saint_of_week = models.ForeignKey(
        "catalog.SaintPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        limit_choices_to={"live": True},
        help_text="Leave empty to hide Saint of the Week. The saint's portrait is shown only "
                  "when its portrait credit is filled.",
    )
    saint_of_week_line = models.CharField(
        max_length=160, blank=True, help_text="One short line for children, shown under the name.",
    )

    church_status_note = models.CharField(
        max_length=255, blank=True,
        default="Church status information should be checked against official sources.",
        help_text="The Church-status line in the Future Saints footer, on every Future Saints page.",
    )

    parent_page_types = ["home.HomePage"]
    subpage_types = ["future_saints.FutureSaintsIndexPage"]
    max_count = 1

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
            heading="Saint of the Week",
        ),
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
        return _art(self.hero_illustration, self.hero_illustration_alt, self.hero_illustration_credit)

    def _card(self, prefix, request):
        page = getattr(self, f"{prefix}_page")
        return {
            "title": getattr(self, f"{prefix}_title"),
            "line": getattr(self, f"{prefix}_line"),
            "page": page,
            "url": _live_url(page, request),
            "icon": KIND_ICONS.get(page.content_kind, SLOT_ICONS[prefix]) if page else SLOT_ICONS[prefix],
            "accent": getattr(self, f"{prefix}_accent"),
            "art": _art(
                getattr(self, f"{prefix}_illustration"),
                getattr(self, f"{prefix}_illustration_alt"),
                getattr(self, f"{prefix}_illustration_credit"),
            ),
            "slot": prefix.replace("_", " "),
        }

    def saint_of_week_card(self):
        saint = self.saint_of_week
        if saint is None or not saint.live:
            return None
        portrait = None
        if saint.portrait_id and (saint.portrait_credit or "").strip():
            portrait = {"image": saint.portrait, "alt": f"Portrait of {saint.title}",
                        "credit": saint.portrait_credit.strip()}
        return {"name": saint.title, "line": self.saint_of_week_line, "art": portrait}

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        cards = [self._card(f"card_{n}", request) for n in (1, 2, 3, 4)]
        holy_land = self._card("holy_land", request)
        saint = self.saint_of_week_card()
        context["fs_cards"] = cards
        context["fs_holy_land"] = holy_land
        context["fs_saint"] = saint
        shown = [self.hero_art] + [c["art"] for c in cards] + [holy_land["art"]] + [saint and saint["art"]]
        context["fs_credits"] = [a["credit"] for a in shown if a]
        return context


class FutureSaintsIndexPage(FutureSaintsGateMixin, Page):
    content_kind = models.CharField(max_length=30, blank=True, choices=CONTENT_KIND_CHOICES)
    intro = models.TextField(max_length=400, blank=True, help_text="One or two short sentences for children.")
    accent = models.CharField(max_length=20, blank=True, choices=ACCENT_CHOICES)
    banner_illustration = _image_field("Shown only when the credit below is filled.")
    banner_illustration_alt = models.CharField(max_length=200, blank=True)
    banner_illustration_credit = models.CharField(max_length=255, blank=True)

    parent_page_types = ["future_saints.FutureSaintsHomePage"]
    # Each index takes only the learning type matching its content_kind;
    # LearningPage.can_create_at() narrows this list per index.
    subpage_types = [
        "future_saints.SaintLearningPage",
        "future_saints.MarianLearningPage",
        "future_saints.EucharisticLearningPage",
        "future_saints.HolyLandLearningPage",
        "future_saints.MissionLearningPage",
    ]

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
        return _art(self.banner_illustration, self.banner_illustration_alt, self.banner_illustration_credit)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["fs_children"] = [p.specific for p in self.get_children().live().public().order_by("path")]
        context["fs_type_icon"] = KIND_ICONS.get(self.content_kind, "mark")
        art = self.banner_art
        context["fs_credits"] = [art["credit"]] if art else []
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
