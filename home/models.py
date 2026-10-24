"""
Page models for Sites of Grace.

HomePage is now a fully editable, section-based homepage. Every strip
(feature cards, featured sites, featured saints, journey bullets, store picks,
partners) is an editable, reorderable InlinePanel — no hardcoded content, no
JSON blobs.

Featured Sites / Featured Saints use a page chooser so they point at real pages
as a single source of truth. Until SitePage / SaintPage exist and have featured
images, use the optional image/title override on each row (or leave the strip
empty); once those models land we switch the template to auto-pull image + title
from the linked page and the overrides become unnecessary.
"""
import logging
from datetime import date, timedelta

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.http import HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, PageChooserPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.blocks import (
    BooleanBlock,
    CharBlock,
    ChoiceBlock,
    PageChooserBlock,
    RichTextBlock,
    StructBlock,
    StructValue,
    TextBlock,
)
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Orderable, Page, Site
from wagtail.rich_text import expand_db_html

from catalog.models import (
    CATEGORY_STYLES,
    DEFAULT_CATEGORY_STYLE,
    MAP_PAGE_SLUG,
    TRAIL_COLORS,
    PilgrimageTrailPage,
    SacredSitePage,
    SaintPage,
)
from contact import forms as contact_forms
from contact import models as contact_models
from contact import notify as contact_notify
from contact import turnstile as contact_turnstile
from core import ratelimit
from home import legal, support
from liturgy.today import date_at_noon, liturgical_today, upcoming_feasts
from pilgrims.views import _ip_hash

logger = logging.getLogger(__name__)

# RichTextField feature sets are restricted (no headings/images/lists) so the
# editor can only produce what the "Our Story" typography already handles --
# a paragraph, bold/italic emphasis, and the occasional link.
PROSE_FEATURES = ["bold", "italic", "link"]

# Explore-hub card colors, keyed by the (StandardPage) category page's slug --
# reuses the same fill/stroke/dot tokens as the interactive map's category
# styles so hub tiles, map pins, and directory chips all agree.
HUB_CARD_STYLES = {
    "marian-apparitions": CATEGORY_STYLES["Marian Apparition"],
    "eucharistic-miracles": CATEGORY_STYLES["Eucharistic Miracle"],
    "saints-and-tombs": CATEGORY_STYLES["Saints & Tombs"],
    "holy-lands": CATEGORY_STYLES["Holy Land"],
    "shrines-and-basilicas": CATEGORY_STYLES["Shrine & Basilica"],
    "saints": CATEGORY_STYLES["Saints & Tombs"],
    "pilgrimage-routes": {
        "fill": TRAIL_COLORS["gold"],
        "stroke": TRAIL_COLORS["navy"],
        "dot": TRAIL_COLORS["navy"],
    },
}


class HomePage(Page):
    # --- Hero ---
    hero_heading = models.CharField(
        max_length=160,
        blank=True,
        default="Discover sacred places. Track your journey. Deepen your faith.",
    )
    hero_intro = models.TextField(
        blank=True,
        default=(
            "Explore Marian apparitions, Eucharistic miracles, saints' tombs, sacred "
            "shrines, and Catholic pilgrimage destinations around the world."
        ),
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    primary_cta_text = models.CharField(max_length=40, blank=True, default="Explore the Map")
    primary_cta_link = models.CharField(max_length=255, blank=True, default="/interactive-map/")
    secondary_cta_text = models.CharField(max_length=40, blank=True, default="Begin Your Journey")
    secondary_cta_link = models.CharField(max_length=255, blank=True, default="#")

    # --- Section headings (editable) ---
    featured_sites_heading = models.CharField(
        max_length=80, blank=True, default="Featured Sites and Saints",
        help_text="Heading for the combined sites + saints bucket at the left of the pilgrim band.",
    )
    # Retained so existing content isn't dropped; the store bucket no longer
    # renders on the homepage (the subscription bucket replaced it).
    store_heading = models.CharField(max_length=80, blank=True, default="Books, Films & More")

    # --- Community teaser ("Your Journey, Your Story") ---
    community_heading = models.CharField(max_length=120, blank=True, default="Your Journey, Your Story")
    community_intro = models.TextField(
        blank=True,
        default=(
            "Create your personal pilgrim profile, track the sacred places you have "
            "visited, save future destinations, upload photos, and share the moments "
            "that deepened your faith."
        ),
    )
    community_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    # Logged-out fallback CTA -- logged-in visitors see a hardcoded "My Pilgrim
    # Passport" link to /passport/ instead (home_page.html), since that
    # destination depends on auth state rather than editorial choice.
    community_cta_text = models.CharField(max_length=40, blank=True, default="Begin Your Journey")
    community_cta_link = models.CharField(max_length=255, blank=True, default="/accounts/signup/")

    # --- Subscription bucket ("Pilgrimage From Home") ---
    # Retained so existing content isn't dropped; the bucket no longer renders
    # on the homepage (the Today in the Church card replaced it).
    subscription_heading = models.CharField(
        max_length=80, blank=True, default="Pilgrimage From Home",
        help_text="Small heading across the top of the bucket.",
    )
    subscription_title = models.CharField(
        max_length=120, blank=True, default="The Pilgrim's Box",
        help_text="Name of the subscription, shown large under the image.",
    )
    subscription_intro = models.TextField(
        blank=True,
        default=(
            "Four times a year a package arrives from a different holy place \u2014 real "
            "devotionals sourced from the shrine itself, with a letter that tells the "
            "story behind them."
        ),
    )
    subscription_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Large image for the bucket. Use a tall/portrait crop \u2014 it is "
                  "displayed the same way as the Your Journey photo.",
    )
    subscription_price_line = models.CharField(
        max_length=80, blank=True, default="$54 a quarter \u00b7 cancel anytime",
    )
    subscription_product = models.ForeignKey(
        "store.StoreProduct", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Choose the subscription product to show its email "
                  "waitlist form right here on the homepage. Leave blank to show a "
                  "plain button instead.",
    )
    subscription_cta_text = models.CharField(max_length=40, blank=True, default="Join the Waitlist")
    subscription_cta_link = models.CharField(
        max_length=255, blank=True, default="/store/",
        help_text="Where the button goes when no product is chosen above.",
    )

    # --- Today in the Church (right of the pilgrim band) ---
    calendar_enabled = models.BooleanField(
        default=True,
        help_text="Show today's liturgical calendar card in the pilgrim band.",
    )
    calendar_heading = models.CharField(max_length=60, blank=True, default="Today in the Church")
    calendar_footer_link_text = models.CharField(
        max_length=60, blank=True, default="Browse saints by feast day",
    )
    calendar_footer_link = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to the saints directory.",
    )

    # --- Partners ---
    partners_heading = models.CharField(max_length=80, blank=True, default="Pilgrimage Partners")
    partners_quote = models.CharField(max_length=200, blank=True)
    partners_quote_source = models.CharField(max_length=80, blank=True)

    # --- News feed ---
    news_heading = models.CharField(max_length=120, blank=True, default="News from the Sacred Places")
    news_intro = models.TextField(
        blank=True,
        default=(
            "Shrine announcements, pilgrimage news, feast celebrations, and events "
            "— from trusted Catholic newsrooms."
        ),
    )
    news_enabled = models.BooleanField(default=True)
    news_count = models.IntegerField(default=6)

    # --- v2 homepage (only rendered behind SOG_V2_ENABLED) ---
    # "Explore by destination" tiles come from live destination hubs, in the
    # order of the destination_tiles rows if any are set, else by title.
    upcoming_enabled = models.BooleanField(
        default=True, help_text='Show "Upcoming feasts" on the v2 homepage.',
    )
    upcoming_heading = models.CharField(
        max_length=120, blank=True, default="Feasts coming up, and where to keep them",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_heading"),
                FieldPanel("hero_intro"),
                FieldPanel("hero_image"),
                FieldPanel("primary_cta_text"),
                FieldPanel("primary_cta_link"),
                FieldPanel("secondary_cta_text"),
                FieldPanel("secondary_cta_link"),
            ],
            heading="Hero",
        ),
        InlinePanel("feature_cards", heading="Feature cards", max_num=8),
        MultiFieldPanel(
            [
                FieldPanel("featured_sites_heading"),
                InlinePanel("featured_sites", label="Featured site", max_num=2),
                InlinePanel("featured_saints", label="Featured saint", max_num=2),
            ],
            heading="Featured Sites and Saints",
        ),
        MultiFieldPanel(
            [
                FieldPanel("community_heading"),
                FieldPanel("community_intro"),
                FieldPanel("community_image"),
                FieldPanel("community_cta_text"),
                FieldPanel("community_cta_link"),
                InlinePanel("journey_bullets", label="Journey bullet", max_num=6),
            ],
            heading="Community teaser",
        ),
        MultiFieldPanel(
            [
                FieldPanel("calendar_enabled"),
                FieldPanel("calendar_heading"),
                FieldPanel("calendar_footer_link_text"),
                PageChooserPanel("calendar_footer_link"),
            ],
            heading="Today in the Church",
        ),
        MultiFieldPanel(
            [
                FieldPanel("partners_heading"),
                FieldPanel("partners_quote"),
                FieldPanel("partners_quote_source"),
                InlinePanel("partners", label="Partner"),
            ],
            heading="Partners",
        ),
        MultiFieldPanel(
            [
                FieldPanel("news_heading"),
                FieldPanel("news_intro"),
                FieldPanel("news_enabled"),
                FieldPanel("news_count"),
            ],
            heading="News feed",
        ),
        MultiFieldPanel(
            [InlinePanel("destination_tiles", max_num=8, label="Destination tile")],
            heading="Explore by destination (v2 homepage)",
            classname="collapsed",
        ),
        MultiFieldPanel(
            [FieldPanel("upcoming_enabled"), FieldPanel("upcoming_heading")],
            heading="Upcoming feasts (v2 homepage)",
            classname="collapsed",
        ),
    ]

    max_count = 1
    subpage_types = ["home.AboutPage", "home.MapPage", "home.StandardPage", "home.StorePage", "home.SupportPage", "home.ContactPage", "blog.BlogIndexPage", "destinations.DestinationIndexPage"]

    class Meta:
        verbose_name = "Home page"

    def get_context(self, request):
        context = super().get_context(request)

        try:
            from news.models import TOPIC_CHOICES, NewsItem, NewsSource
            news_items = list(
                NewsItem.objects.filter(hidden=False).select_related("source")[:self.news_count]
            )
            present_topics = {item.topic for item in news_items}
            context["news_items"] = news_items
            context["news_topics"] = [(v, label) for v, label in TOPIC_CHOICES if v in present_topics]
            context["news_last_updated"] = NewsSource.objects.filter(
                enabled=True, last_fetched__isnull=False
            ).order_by("-last_fetched").values_list("last_fetched", flat=True).first()
        except Exception:
            context["news_items"] = []
            context["news_topics"] = []
            context["news_last_updated"] = None

        context["calendar_footer_url"] = self._calendar_footer_url()
        context["liturgical"] = None
        from core.v2 import v2_enabled

        v2 = v2_enabled(request)
        if v2:
            # The v2 homepage drops the three-column band (and with it Today in
            # the Church) and News; their fields, the liturgy app and the
            # fetch-news job all stay. It adds destinations and upcoming feasts.
            context["destination_tiles"] = self.destination_hub_tiles()
            context["destinations_index"] = self._destinations_index()
            context["upcoming_feasts"] = []
            if self.upcoming_enabled:
                try:
                    context["upcoming_feasts"] = upcoming_feasts(now=self._calendar_now(request))
                except Exception:
                    logger.exception("Upcoming feasts band failed to build")
        if self.calendar_enabled and not v2:
            try:
                liturgical = liturgical_today(self._calendar_now(request))
                context["liturgical"] = liturgical
                # Today first, so without JS the other two days read as
                # compact lines underneath it.
                context["liturgical_panels"] = [
                    {"key": key, "name": name, "day": liturgical[key]}
                    for key, name in (("today", "Today"), ("yesterday", "Yesterday"), ("tomorrow", "Tomorrow"))
                ]
            except Exception:
                # The card falls back to a plain "Explore the saints" link;
                # the home page itself must never fail because of it.
                logger.exception("Today in the Church card failed to build")

        return context

    def destination_hub_tiles(self):
        """Up to 8 live, public hubs: the chosen tiles in order, else by title."""
        from destinations.models import DestinationHubPage

        live = DestinationHubPage.objects.live().public()
        chosen = [tile.hub for tile in self.destination_tiles.select_related("hub") if tile.hub_id]
        if chosen:
            live_ids = set(live.filter(pk__in=[h.pk for h in chosen]).values_list("pk", flat=True))
            return [hub for hub in chosen if hub.pk in live_ids][:8]
        return list(live.order_by("title")[:8])

    @staticmethod
    def _destinations_index():
        from destinations.models import DestinationIndexPage

        return DestinationIndexPage.objects.live().public().first()

    @staticmethod
    def _calendar_now(request):
        """DEBUG-only ?_date=YYYY-MM-DD, for screenshots of other days."""
        if not settings.DEBUG:
            return None
        raw = request.GET.get("_date", "")
        try:
            return date_at_noon(date.fromisoformat(raw)) if raw else None
        except ValueError:
            return None

    def _calendar_footer_url(self):
        if self.calendar_footer_link_id and self.calendar_footer_link.live:
            return self.calendar_footer_link.url
        saints = StandardPage.objects.live().public().filter(layout="saints_directory").first()
        return saints.url if saints else "/explore/"


class HomeDestinationTile(Orderable):
    """The order of the v2 homepage's "Explore by destination" tiles."""

    page = ParentalKey("home.HomePage", on_delete=models.CASCADE, related_name="destination_tiles")
    hub = models.ForeignKey("destinations.DestinationHubPage", on_delete=models.CASCADE, related_name="+")

    panels = [PageChooserPanel("hub", "destinations.DestinationHubPage")]


class FeatureCard(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="feature_cards")
    icon = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    title = models.CharField(max_length=80)
    blurb = models.TextField(blank=True)
    link_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    link_url = models.CharField(max_length=255, blank=True, help_text="Used only if no page is chosen.")
    link_text = models.CharField(max_length=40, blank=True, default="Learn More")

    panels = [
        FieldPanel("icon"),
        FieldPanel("title"),
        FieldPanel("blurb"),
        PageChooserPanel("link_page"),
        FieldPanel("link_url"),
        FieldPanel("link_text"),
    ]


class FeaturedSite(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="featured_sites")
    site_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Choose the sacred site page to feature.",
    )
    image_override = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to the site page's own image once available.",
    )
    title_override = models.CharField(max_length=120, blank=True, help_text="Optional. Defaults to the page title.")

    panels = [
        PageChooserPanel("site_page"),
        FieldPanel("image_override"),
        FieldPanel("title_override"),
    ]

    @property
    def display_title(self):
        if self.title_override:
            return self.title_override
        return self.site_page.title if self.site_page else ""

    @property
    def display_image(self):
        if self.image_override:
            return self.image_override
        return getattr(self.site_page.specific, "featured_image", None) if self.site_page else None

    @property
    def locality_line(self):
        if not self.site_page:
            return ""
        specific = self.site_page.specific
        parts = [getattr(specific, "locality", ""), getattr(specific, "country", "")]
        return ", ".join(part for part in parts if part)


class FeaturedSaint(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="featured_saints")
    saint_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Choose the saint page to feature.",
    )
    image_override = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    title_override = models.CharField(max_length=120, blank=True)

    panels = [
        PageChooserPanel("saint_page"),
        FieldPanel("image_override"),
        FieldPanel("title_override"),
    ]

    @property
    def display_title(self):
        if self.title_override:
            return self.title_override
        return self.saint_page.title if self.saint_page else ""

    @property
    def display_image(self):
        if self.image_override:
            return self.image_override
        return getattr(self.saint_page.specific, "portrait", None) if self.saint_page else None

    @property
    def locality_line(self):
        """Feast day, so saint tiles carry a second line like site tiles do."""
        if not self.saint_page:
            return ""
        return getattr(self.saint_page.specific, "feast_day", "")


class JourneyBullet(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="journey_bullets")
    title = models.CharField(max_length=80)
    text = models.CharField(max_length=200, blank=True)

    panels = [FieldPanel("title"), FieldPanel("text")]


class SubscriptionBullet(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="subscription_bullets")
    text = models.CharField(max_length=120)

    panels = [FieldPanel("text")]


class StorePick(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="store_picks")
    cover = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=120, blank=True)
    price = models.CharField(max_length=20, blank=True)
    link_url = models.CharField(max_length=255, blank=True)

    panels = [
        FieldPanel("cover"),
        FieldPanel("title"),
        FieldPanel("subtitle"),
        FieldPanel("price"),
        FieldPanel("link_url"),
    ]


class Partner(Orderable):
    page = ParentalKey(HomePage, on_delete=models.CASCADE, related_name="partners")
    logo = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    name = models.CharField(max_length=120)
    link_url = models.CharField(max_length=255, blank=True)

    panels = [FieldPanel("logo"), FieldPanel("name"), FieldPanel("link_url")]


# --- Unchanged structural pages from the bones ---

class StandardPage(Page):
    LAYOUT_CHOICES = [
        ("default", "Default"),
        ("explore_hub", "Explore hub (category card grid)"),
        ("category_directory", "Category directory (site card grid)"),
        ("saints_directory", "Saints directory (saint card grid)"),
    ]

    intro = models.TextField(blank=True)
    body = RichTextField(blank=True)
    layout = models.CharField(max_length=30, choices=LAYOUT_CHOICES, default="default")
    teaser = models.CharField(
        max_length=200,
        blank=True,
        help_text="One-line description shown on this page's card when it's linked from a hub page.",
    )
    card_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to a branded color placeholder if not set.",
    )

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("body"),
        MultiFieldPanel(
            [FieldPanel("layout"), FieldPanel("teaser"), FieldPanel("card_image")],
            heading="Hub / directory display",
        ),
    ]

    class Meta:
        verbose_name = "Standard page"

    def get_template(self, request, *args, **kwargs):
        return {
            "explore_hub": "home/explore_hub_page.html",
            "category_directory": "home/directory_page.html",
            "saints_directory": "home/directory_page.html",
        }.get(self.layout, "home/standard_page.html")

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        if self.layout == "explore_hub":
            context["hub_cards"] = self._get_hub_cards()
        elif self.layout in ("category_directory", "saints_directory"):
            context["directory_cards"] = self._get_directory_cards()
        return context

    def _hub_card(self, child, clickable):
        return {
            "title": child.title,
            "teaser": getattr(child, "teaser", ""),
            "image": getattr(child, "card_image", None),
            "url": child.url if clickable else None,
            "clickable": clickable,
            "style": HUB_CARD_STYLES.get(child.slug, DEFAULT_CATEGORY_STYLE),
        }

    @staticmethod
    def _hub_card_is_clickable(child):
        """Pilgrimage Routes was a placeholder card with nowhere to go.

        Rather than keep that hardcoded, the card lights up on its own the
        moment the routes page has a live child -- so the first published
        trail is what makes it clickable, and nothing has to be remembered
        and changed by hand later.
        """
        if child.slug != "pilgrimage-routes":
            return True
        return child.get_children().live().exists()

    def _get_hub_cards(self):
        cards = [
            self._hub_card(child, clickable=self._hub_card_is_clickable(child))
            for child in self.get_children().live().specific()
        ]
        saints_page = Page.objects.live().filter(slug="saints").first()
        if saints_page:
            insert_at = len(cards) - 1 if cards and cards[-1]["title"] == "Pilgrimage Routes" else len(cards)
            cards.insert(insert_at, self._hub_card(saints_page.specific, clickable=True))
        return cards

    def _get_directory_cards(self):
        cards = []
        for child in self.get_children().live().specific():
            if isinstance(child, SacredSitePage):
                cards.append({
                    "title": child.title,
                    "chip": child.category,
                    "style": CATEGORY_STYLES.get(child.category, DEFAULT_CATEGORY_STYLE),
                    "bio": child.summary_short,
                    "url": child.url,
                })
            elif isinstance(child, SaintPage):
                cards.append({
                    "title": child.title,
                    "meta": child.feast_day,
                    "bio": child.significance,
                    "url": child.url,
                })
            elif isinstance(child, PilgrimageTrailPage):
                # A trail's chip is its own line color, so the directory card
                # and the line on the map read as the same object.
                cards.append({
                    "title": child.title,
                    "chip": child.trail_type,
                    "style": {
                        "fill": child.line_hex,
                        "stroke": child.line_hex,
                        "dot": "#FDF9F2",
                    },
                    "meta": child.length_display,
                    "bio": child.summary_short,
                    "url": child.url,
                })
        return cards


class MapPage(Page):
    intro = models.TextField(
        blank=True,
        default="Every pin is a sacred site. Filter by category, then open a site to read its story.",
    )
    content_panels = Page.content_panels + [FieldPanel("intro")]
    max_count = 1
    template = "home/map_page.html"

    class Meta:
        verbose_name = "Interactive map page"


class StorePage(Page):
    """The original store stub.

    It now renders the same product listing as store.StoreIndexPage, so whichever
    of the two is live at /store/ shows the catalog. Run
    `python manage.py store_pages` to see which one that is.
    """

    intro = models.TextField(
        blank=True,
        default="Prayer resources, study guides, and pilgrimage keepsakes — coming soon.",
    )
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("body")]

    class Meta:
        verbose_name = "Store page"

    def get_context(self, request):
        context = super().get_context(request)
        from store.models import store_listing_context

        context.update(store_listing_context(request))
        return context


# --- About ("Our Story") -----------------------------------------------

# Shared by PillarBlock.icon and includes/_line_icon.html -- the include
# covers exactly these seven values, so a new choice here needs a matching
# <symbol> added there too.
ICON_CHOICES = [
    ("globe", "Globe"),
    ("book", "Book"),
    ("map", "Map"),
    ("camera", "Camera"),
    ("church", "Church"),
    ("cross", "Cross"),
    ("heart", "Heart"),
]


def _map_or_explore_url():
    """The interactive map, or the Explore hub if the map isn't live yet.

    Both are real "go see the sacred sites" destinations -- the map is tried
    first to match HomePage's own hero CTA (primary_cta_link default
    "/interactive-map/"). Returns "" (never "#") if neither exists yet, so a
    fresh install with no page tree beneath Home doesn't render a dead link.
    """
    for slug in (MAP_PAGE_SLUG, "explore"):
        page = Page.objects.live().public().filter(slug=slug).first()
        if page:
            return page.url
    return ""


def _passport_url():
    """The pilgrim passport view -- a plain Django route, not a Wagtail page."""
    try:
        return reverse("passport")
    except NoReverseMatch:
        return ""


class PillarBlock(StructBlock):
    icon = ChoiceBlock(choices=ICON_CHOICES)
    title = CharBlock(max_length=40)
    text = TextBlock()

    class Meta:
        icon = "pick"
        label = "Pillar"


class BecomingCardValue(StructValue):
    """Resolves each card's link the same way the page-level CTAs do --

    an editor-chosen page wins; otherwise a card falls back by title to the
    one real destination that copy is asking for (mirrors the icon-by-title
    matching already used for HomePage's journey bullets). "Plan Your
    Pilgrimage" has no guides page yet, so it has no fallback and the card
    renders with no link at all rather than a "#".
    """

    @property
    def resolved_url(self):
        link_page = self.get("link_page")
        if link_page and link_page.live:
            return link_page.url
        title = self.get("title")
        if title == "Explore Sacred Places":
            return _map_or_explore_url()
        if title == "Create Your Pilgrim Story":
            return _passport_url()
        return ""


class CardBlock(StructBlock):
    image = ImageChooserBlock(required=False)
    title = CharBlock(max_length=80)
    text = TextBlock()
    link_label = CharBlock(max_length=40)
    link_page = PageChooserBlock(required=False)

    class Meta:
        icon = "doc-full"
        label = "Card"
        value_class = BecomingCardValue


class AboutPage(Page):
    """The "Our Story" page -- mission + founder story.

    Single, editor-managed About page. Every field is prefilled with the
    launch copy as its default= so Steven can Add child page -> Our Story
    page and publish with no other setup; he only adds photos.
    """

    # --- Hero ---
    hero_eyebrow = models.CharField(max_length=60, blank=True, default="Our Mission")
    hero_title = models.CharField(
        max_length=120, blank=True,
        default="Helping People Discover the Places Where Faith Comes Alive",
    )
    hero_intro = models.TextField(
        blank=True,
        default=(
            "Sites of Grace was created to help Catholics and fellow pilgrims discover the "
            "sacred places, extraordinary stories, and holy people that have shaped the "
            "Church — and to make experiencing those places easier for everyone."
        ),
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    hero_cta_label = models.CharField(max_length=40, blank=True, default="Explore Sacred Sites")
    hero_cta_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to the interactive map / Explore hub if left blank.",
    )

    # --- Why Sites of Grace Exists ---
    why_eyebrow = models.CharField(max_length=60, blank=True, default="Why Sites of Grace Exists")
    why_title = models.CharField(max_length=120, blank=True, default="Connecting People With Sacred Places")
    why_body = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        default=(
            "<p>Sites of Grace exists to connect people with the places where generations of "
            "Catholics have encountered God in extraordinary ways.</p>"
            "<p>From Marian apparition sites and Eucharistic miracles to the tombs of saints, "
            "ancient churches, pilgrimage routes, and sacred places throughout the world, our "
            "goal is to make these destinations easier to discover, understand, and "
            "experience.</p>"
            "<p>But Sites of Grace is about more than travel. It is about helping people "
            "understand why these places matter — the stories behind them, the people whose "
            "lives were changed there, and the faith that continues to draw pilgrims centuries "
            "later.</p>"
        ),
    )
    pillars = StreamField(
        [("pillar", PillarBlock())],
        max_num=4,
        blank=True,
        default=[
            {"type": "pillar", "value": {
                "icon": "globe", "title": "Discover",
                "text": "Find sacred sites around the world.",
            }},
            {"type": "pillar", "value": {
                "icon": "book", "title": "Learn",
                "text": "Understand the history, miracles, saints, and traditions connected to them.",
            }},
            {"type": "pillar", "value": {
                "icon": "map", "title": "Prepare",
                "text": "Use practical pilgrimage guides to plan meaningful visits.",
            }},
            {"type": "pillar", "value": {
                "icon": "camera", "title": "Remember",
                "text": (
                    "Record the places you have visited and the experiences you encountered "
                    "along the way."
                ),
            }},
        ],
    )

    # --- How It Began ---
    began_eyebrow = models.CharField(max_length=60, blank=True, default="How It Began")
    began_title = models.CharField(max_length=120, blank=True, default="A Pilgrimage That Changed Everything")
    began_body = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        default=(
            "<p>Sites of Grace began with a pilgrimage.</p>"
            "<p>What started as a journey to pray for someone deeply loved became something "
            "much larger — a realization that there are extraordinary places throughout the "
            "world where people have traveled for generations seeking healing, peace, "
            "conversion, and a deeper relationship with God.</p>"
            "<p>Along the way, I discovered how difficult it could be to find all of that "
            "information in one place. The history might be on one website, Mass times on "
            "another, travel information somewhere else, and some of the most meaningful "
            "stories were difficult to find at all.</p>"
            "<p>I began imagining a place where a pilgrim could discover a sacred site, "
            "understand its story, prepare for the journey, and carry that experience with "
            "them afterward. That idea became Sites of Grace.</p>"
        ),
    )
    began_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    # --- About the Founder ---
    founder_eyebrow = models.CharField(max_length=60, blank=True, default="About the Founder")
    founder_name = models.CharField(max_length=120, blank=True, default="Steven Fyffe")
    founder_role = models.CharField(max_length=120, blank=True, default="Founder, Sites of Grace")
    founder_bio = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        default=(
            "<p>Steven created Sites of Grace after his own journey of discovering the "
            "Catholic faith and experiencing firsthand the power of pilgrimage.</p>"
            "<p>His travels to sacred places — including Marian shrines, historic churches, "
            "and sites connected with the saints — sparked a desire to create a resource "
            "that could help others experience these places with greater understanding and "
            "purpose.</p>"
            "<p>Sites of Grace grew from a simple idea: if someone feels called to visit a "
            "sacred place, finding its story and planning the journey shouldn't be "
            "difficult.</p>"
        ),
    )
    founder_photo = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Brand editorial portrait, not a pilgrim-submitted photo. Renders arched.",
    )

    # --- What We Believe ---
    believe_eyebrow = models.CharField(max_length=60, blank=True, default="What We Believe")
    believe_heading = models.TextField(
        blank=True,
        help_text="A line break here renders as a line break on the page.",
        default=(
            "Pilgrimage Is More Than Going Somewhere.\n"
            "It Is Allowing the Journey to Change You."
        ),
    )
    believe_body = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        help_text=(
            "Two paragraphs. The gold emphasis line below is rendered between them."
        ),
        default=(
            "<p>For centuries, Christians have left the familiarity of home to journey toward "
            "sacred places. They traveled carrying prayers, gratitude, questions, sorrow, and "
            "hope.</p>"
            "<p>Sometimes the destination is across the world. Sometimes it is a shrine an "
            "hour from home. What matters is the intention with which the journey begins.</p>"
        ),
    )
    believe_emphasis = models.CharField(
        max_length=120, blank=True, default="We believe pilgrimage still matters.",
    )
    believe_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    # --- What Sites of Grace Is Becoming ---
    becoming_eyebrow = models.CharField(
        max_length=60, blank=True, default="What Sites of Grace Is Becoming",
    )
    becoming_cards = StreamField(
        [("card", CardBlock())],
        max_num=3,
        blank=True,
        default=[
            {"type": "card", "value": {
                "title": "Explore Sacred Places",
                "text": (
                    "Marian apparitions, Eucharistic miracles, saints, shrines, churches, "
                    "missions, and other places of Catholic significance."
                ),
                "link_label": "Open the map",
            }},
            {"type": "card", "value": {
                "title": "Plan Your Pilgrimage",
                "text": (
                    "Practical travel guides, itineraries, Mass and confession information, "
                    "accessibility guidance, lodging, transportation, and local "
                    "recommendations."
                ),
                "link_label": "See the guides",
            }},
            {"type": "card", "value": {
                "title": "Create Your Pilgrim Story",
                "text": (
                    "Track the sites you have visited, save photographs, preserve memories, "
                    "and share your experiences with other pilgrims."
                ),
                "link_label": "Start your passport",
            }},
        ],
    )

    # --- Closing Call to Action ---
    closing_title = models.CharField(max_length=120, blank=True, default="Where Will Your Journey Begin?")
    closing_text = models.TextField(
        blank=True,
        default=(
            "There are thousands of sacred places throughout the world, each carrying a "
            "story of faith worth discovering."
        ),
    )
    closing_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    closing_primary_label = models.CharField(max_length=40, blank=True, default="Explore Sites")
    closing_primary_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to the interactive map / Explore hub if left blank.",
    )
    closing_secondary_label = models.CharField(max_length=40, blank=True, default="Learn About Pilgrimage")
    closing_secondary_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. No fallback -- the button is hidden until a page is chosen here.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_eyebrow"),
                FieldPanel("hero_title"),
                FieldPanel("hero_intro"),
                FieldPanel("hero_image"),
                FieldPanel("hero_cta_label"),
                PageChooserPanel("hero_cta_page"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("why_eyebrow"),
                FieldPanel("why_title"),
                FieldPanel("why_body"),
                FieldPanel("pillars"),
            ],
            heading="Why Sites of Grace Exists",
        ),
        MultiFieldPanel(
            [
                FieldPanel("began_eyebrow"),
                FieldPanel("began_title"),
                FieldPanel("began_body"),
                FieldPanel("began_image"),
            ],
            heading="How It Began",
        ),
        MultiFieldPanel(
            [
                FieldPanel("founder_eyebrow"),
                FieldPanel("founder_name"),
                FieldPanel("founder_role"),
                FieldPanel("founder_bio"),
                FieldPanel("founder_photo"),
            ],
            heading="About the Founder",
        ),
        MultiFieldPanel(
            [
                FieldPanel("believe_eyebrow"),
                FieldPanel("believe_heading"),
                FieldPanel("believe_body"),
                FieldPanel("believe_emphasis"),
                FieldPanel("believe_image"),
            ],
            heading="What We Believe",
        ),
        MultiFieldPanel(
            [
                FieldPanel("becoming_eyebrow"),
                FieldPanel("becoming_cards"),
            ],
            heading="What Sites of Grace Is Becoming",
        ),
        MultiFieldPanel(
            [
                FieldPanel("closing_title"),
                FieldPanel("closing_text"),
                FieldPanel("closing_image"),
                FieldPanel("closing_primary_label"),
                PageChooserPanel("closing_primary_page"),
                FieldPanel("closing_secondary_label"),
                PageChooserPanel("closing_secondary_page"),
            ],
            heading="Closing Call to Action",
        ),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1
    template = "home/about_page.html"

    class Meta:
        verbose_name = "Our Story page"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only for a brand-new, unsaved instance -- e.g. the blank form
        # "Add child page" opens -- so an existing page's own slug is never
        # touched.
        if not self.pk and not self.slug:
            self.slug = "our-story"

    @property
    def hero_cta_url(self):
        if self.hero_cta_page_id and self.hero_cta_page.live:
            return self.hero_cta_page.url
        return _map_or_explore_url()

    @property
    def closing_primary_url(self):
        if self.closing_primary_page_id and self.closing_primary_page.live:
            return self.closing_primary_page.url
        return _map_or_explore_url()

    @property
    def closing_secondary_url(self):
        """No sensible sitewide fallback exists for this one yet, so the
        button simply doesn't render until an editor picks a page."""
        if self.closing_secondary_page_id and self.closing_secondary_page.live:
            return self.closing_secondary_page.url
        return ""

    @property
    def believe_body_parts(self):
        """(opening paragraph, remaining paragraphs) so believe_emphasis can
        render between them while believe_body stays a single RichTextField."""
        html = str(self.believe_body or "")
        marker = "</p>"
        idx = html.find(marker)
        if idx == -1:
            return {"first": html, "rest": ""}
        return {"first": html[: idx + len(marker)], "rest": html[idx + len(marker):]}


# --- Support ------------------------------------------------------------

# The Support page's "helps" cards and "other ways" list: the shared line
# set plus the mockup's own icons. A separate list (not an addition to
# ICON_CHOICES) so AboutPage's pillar choices -- and its migrations -- are
# untouched. includes/_line_icon.html has a branch for every value here.
SUPPORT_ICON_CHOICES = ICON_CHOICES + [
    ("server", "Server"),
    ("document", "Document"),
    ("pin", "Map pin"),
    ("share", "Share"),
    ("pencil", "Pencil"),
    ("bookmark", "Bookmark"),
    ("candle", "Candle"),
]


class SupportHelpBlock(StructBlock):
    icon = ChoiceBlock(choices=SUPPORT_ICON_CHOICES)
    title = CharBlock(max_length=60)
    blurb = TextBlock()

    class Meta:
        icon = "pick"
        label = "What support helps with"


class SupportWayBlock(StructBlock):
    icon = ChoiceBlock(choices=SUPPORT_ICON_CHOICES)
    title = CharBlock(max_length=60)
    text = RichTextBlock(features=PROSE_FEATURES)

    class Meta:
        icon = "list-ul"
        label = "Other way to help"


class SupportFaqBlock(StructBlock):
    question = CharBlock(max_length=160)
    answer = RichTextBlock(features=PROSE_FEATURES)
    show_manage_link = BooleanBlock(
        required=False,
        help_text=(
            'Adds a "Manage your monthly support" link under the answer, '
            "only while the page's manage URL is set."
        ),
    )

    class Meta:
        icon = "help"
        label = "Question"


def _live_page_at(path):
    """The live, public page served at `path` ("/contact/") on the default
    site, or None."""
    site = Site.objects.filter(is_default_site=True).select_related("root_page").first()
    if not site:
        return None
    url_path = site.root_page.url_path + path.strip("/") + "/"
    return Page.objects.live().public().filter(url_path=url_path).first()


def default_support_ways():
    """The "Other Ways to Help" launch copy.

    A callable, so the two links resolve when an editor opens Add child page
    -> Support page, not when the migration was written: "Tell us" links to
    the Contact page (?topic=suggest) and "How this works" to the Affiliate
    Disclosure page -- or the Store page, which carries the disclosure --
    only if a live page exists there. Otherwise that text renders unlinked.
    """
    contact = _live_page_at("/contact/")
    tell_us = (
        f'<a href="{contact.url}?topic=suggest">Tell us</a>' if contact else "Tell us"
    )
    disclosure = _live_page_at("/affiliate-disclosure/") or _live_page_at("/store/")
    how_it_works = (
        f' <a linktype="page" id="{disclosure.pk}">How this works</a>' if disclosure else ""
    )
    return [
        {"type": "way", "value": {
            "icon": "share", "title": "Share a site",
            "text": (
                "<p>Send a page to someone planning a trip, or share it with your "
                "parish.</p>"
            ),
        }},
        {"type": "way", "value": {
            "icon": "pencil", "title": "Suggest or correct",
            "text": (
                f"<p>{tell_us} about a place we're missing, or something we got "
                "wrong.</p>"
            ),
        }},
        {"type": "way", "value": {
            "icon": "bookmark", "title": "Shop through our links",
            "text": (
                "<p>Some book and travel links earn us a small commission at no cost "
                f"to you.{how_it_works}</p>"
            ),
        }},
        {"type": "way", "value": {
            "icon": "candle", "title": "Keep us in prayer",
            "text": "<p>For the work, and for every pilgrim who uses it.</p>",
        }},
    ]


class SupportPage(Page):
    """ "Support Sites of Grace" -- optional one-time or monthly support
    through Stripe-hosted Checkout.

    Every copy field is prefilled with the launch copy as its default= so
    Add child page -> Support page opens already written. serve() handles
    the whole flow at the page's own URL: GET renders, POST validates and
    redirects to Stripe, GET ?thanks=1&session_id=... shows the thank-you
    panel for a completed session. Until settings.SUPPORT_ENABLED (both
    Stripe settings present), the give card shows the "opens soon" panel.
    """

    # --- Hero ---
    hero_eyebrow = models.CharField(max_length=60, blank=True, default="Support Sites of Grace")
    hero_title = models.CharField(max_length=120, blank=True, default="Help Keep the Way Open")
    hero_intro = models.TextField(
        blank=True,
        default=(
            "Sites of Grace helps Catholics discover the holy places of our faith, learn "
            "their stories, and plan meaningful pilgrimages. It is free to use, and it "
            "always will be."
        ),
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Without one, the hero uses the brand gradient panel.",
    )

    # --- Why We Ask ---
    why_eyebrow = models.CharField(max_length=60, blank=True, default="Why We Ask")
    why_heading = models.CharField(
        max_length=120, blank=True, default="Independently Built, Freely Shared",
    )
    why_body = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        default=(
            "<p>Sites of Grace is built and maintained independently. Every map, saint's "
            "story, and pilgrimage guide is offered free of charge, and nothing on the site "
            "is locked behind a payment.</p>"
            "<p>If Sites of Grace has helped you find a new pilgrimage site, plan a journey, "
            "or simply learn more about the faith, you're welcome to help support its "
            "continued growth. There's no obligation, and every pilgrim is welcome here "
            "either way.</p>"
        ),
    )
    pull_quote = models.CharField(
        max_length=200, blank=True, default="“Freely you have received; freely give.”",
    )
    pull_quote_cite = models.CharField(max_length=80, blank=True, default="Matthew 10:8")

    # --- What Your Support Helps With ---
    helps_eyebrow = models.CharField(
        max_length=60, blank=True, default="What Your Support Helps With",
    )
    helps = StreamField(
        [("help", SupportHelpBlock())],
        max_num=6,
        blank=True,
        default=[
            {"type": "help", "value": {
                "icon": "server", "title": "Hosting & Upkeep",
                "blurb": "Keeping the site fast, secure, and available to pilgrims around the world.",
            }},
            {"type": "help", "value": {
                "icon": "document", "title": "Research",
                "blurb": "Checking every site and saint against Church and shrine sources.",
            }},
            {"type": "help", "value": {
                "icon": "map", "title": "Maps & Photography",
                "blurb": "Better maps, original photos, and more places on the map.",
            }},
            {"type": "help", "value": {
                "icon": "pin", "title": "New Pilgrimage Guides",
                "blurb": "Plan Your Visit guides and trails for more sacred sites.",
            }},
        ],
    )

    # --- The give card ---
    give_heading = models.CharField(max_length=120, blank=True, default="Support Sites of Grace")
    give_lede = models.CharField(
        max_length=200, blank=True,
        default="Choose an amount. You'll finish on Stripe's secure checkout page.",
    )
    preset_amounts = models.CharField(
        max_length=60, default="5,10,25,50",
        help_text='1 to 6 whole-dollar amounts, separated by commas. An "Other" tile is always added.',
    )
    min_amount = models.IntegerField(
        default=3,
        validators=[
            MinValueValidator(support.ABSOLUTE_MIN_DOLLARS),
            MaxValueValidator(support.ABSOLUTE_MAX_DOLLARS),
        ],
        help_text="Smallest amount accepted, in whole dollars ($1 or more).",
    )
    max_amount = models.IntegerField(
        default=1000,
        validators=[
            MinValueValidator(support.ABSOLUTE_MIN_DOLLARS),
            MaxValueValidator(support.ABSOLUTE_MAX_DOLLARS),
        ],
        help_text="Largest amount accepted, in whole dollars ($1,000 at most).",
    )
    default_amount_once = models.IntegerField(
        default=10, help_text="Preselected for one-time support. Must be one of the amounts above.",
    )
    default_amount_monthly = models.IntegerField(
        default=5, help_text="Preselected for monthly support. Must be one of the amounts above.",
    )
    allow_monthly = models.BooleanField(default=True)
    disclaimer = models.TextField(
        default=(
            "Sites of Grace is independently owned and is not a 501(c)(3) charitable "
            "organization. Contributions are voluntary, support the operation of the "
            "website, and are not tax-deductible. Nothing is given in exchange, and all "
            "content stays free. Monthly support can be cancelled anytime."
        ),
        blank=True,
        help_text=(
            "No longer shown on the site. The Support page now shows the support_intro "
            "text from Settings > Legal notices."
        ),
    )
    soon_heading = models.CharField(max_length=120, blank=True, default="Online Support Opens Soon")
    soon_text = models.TextField(
        blank=True,
        help_text="Shown instead of the form until Stripe is configured. A blank line starts a new paragraph.",
        default=(
            "We're setting up secure online support now. Thank you for thinking of us.\n\n"
            "In the meantime, the ways to help on this page cost nothing at all."
        ),
    )
    thanks_heading = models.CharField(max_length=120, blank=True, default="Thank You")
    thanks_text = models.TextField(
        blank=True,
        default=(
            "Your support helps more people discover the extraordinary places of our faith. "
            "May the saints keep you on your journey."
        ),
    )
    manage_url = models.URLField(
        blank=True,
        help_text=(
            'Stripe customer portal login link. The "Manage monthly support" links '
            "appear only when this is set."
        ),
    )

    # --- Other Ways to Help (sidebar) ---
    ways_heading = models.CharField(max_length=120, blank=True, default="Other Ways to Help")
    ways_intro = models.CharField(
        max_length=200, blank=True,
        default="Some of the most helpful support doesn't cost anything.",
    )
    ways = StreamField(
        [("way", SupportWayBlock())],
        max_num=6,
        blank=True,
        default=default_support_ways,
    )
    free_card_heading = models.CharField(max_length=120, blank=True, default="Always Free")
    free_card_text = models.TextField(
        blank=True,
        default=(
            "Support never unlocks anything extra. Every map, guide, and story stays open "
            "to every pilgrim, whether they give or not."
        ),
    )

    # --- FAQ ---
    faq_eyebrow = models.CharField(max_length=60, blank=True, default="Good to Know")
    faq_heading = models.CharField(max_length=120, blank=True, default="Common Questions")
    faqs = StreamField(
        [("faq", SupportFaqBlock())],
        blank=True,
        default=[
            {"type": "faq", "value": {
                "question": "Is my contribution tax-deductible?",
                "answer": (
                    "<p>No. Sites of Grace is independently owned and is not a 501(c)(3) "
                    "charitable organization, so contributions are not tax-deductible. If "
                    "you'd like to make a tax-deductible gift, please consider your parish "
                    "or a shrine you love.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "What does my support pay for?",
                "answer": (
                    "<p>The costs of running the site: hosting, research, maps and "
                    "photography, and new pilgrimage guides. It helps Sites of Grace keep "
                    "growing while everything stays free to use.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "Do supporters get anything extra?",
                "answer": (
                    "<p>No. Support is a gift toward the work, not a purchase. Every page, "
                    "map, and guide is open to everyone.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "How do I change or cancel monthly support?",
                "answer": (
                    "<p>You can update your card or cancel anytime. Stripe handles it "
                    "securely: enter the email you used, and Stripe sends you a link where "
                    "you can make changes.</p>"
                ),
                "show_manage_link": True,
            }},
            {"type": "faq", "value": {
                "question": "Is my payment information safe?",
                "answer": (
                    "<p>Payments are handled entirely by Stripe, a widely used payment "
                    "processor. Your card details go straight to Stripe and never pass "
                    "through or get stored on Sites of Grace.</p>"
                ),
            }},
        ],
    )

    # --- Home page band ---
    home_band_text = models.CharField(
        max_length=200, blank=True,
        default="Sites of Grace is independently built and free for every pilgrim.",
    )
    home_band_emphasis = models.CharField(
        max_length=200, blank=True,
        default="If it has helped you along the way, you can help it grow.",
    )
    show_home_band = models.BooleanField(
        default=True,
        help_text="A quiet band at the bottom of the home page, linking here.",
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_eyebrow"),
                FieldPanel("hero_title"),
                FieldPanel("hero_intro"),
                FieldPanel("hero_image"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("why_eyebrow"),
                FieldPanel("why_heading"),
                FieldPanel("why_body"),
                FieldPanel("pull_quote"),
                FieldPanel("pull_quote_cite"),
                FieldPanel("helps_eyebrow"),
                FieldPanel("helps"),
            ],
            heading="Why We Ask",
        ),
        MultiFieldPanel(
            [
                FieldPanel("give_heading"),
                FieldPanel("give_lede"),
                FieldPanel("preset_amounts"),
                FieldPanel("min_amount"),
                FieldPanel("max_amount"),
                FieldPanel("default_amount_once"),
                FieldPanel("default_amount_monthly"),
                FieldPanel("allow_monthly"),
                FieldPanel("disclaimer"),
                FieldPanel("manage_url"),
            ],
            heading="Support Form",
        ),
        MultiFieldPanel(
            [
                FieldPanel("soon_heading"),
                FieldPanel("soon_text"),
                FieldPanel("thanks_heading"),
                FieldPanel("thanks_text"),
            ],
            heading="Before Stripe / After Checkout",
        ),
        MultiFieldPanel(
            [
                FieldPanel("ways_heading"),
                FieldPanel("ways_intro"),
                FieldPanel("ways"),
                FieldPanel("free_card_heading"),
                FieldPanel("free_card_text"),
            ],
            heading="Sidebar",
        ),
        MultiFieldPanel(
            [
                FieldPanel("faq_eyebrow"),
                FieldPanel("faq_heading"),
                FieldPanel("faqs"),
            ],
            heading="Common Questions",
        ),
        MultiFieldPanel(
            [
                FieldPanel("show_home_band"),
                FieldPanel("home_band_text"),
                FieldPanel("home_band_emphasis"),
            ],
            heading="Home Page Band",
        ),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1
    template = "home/support_page.html"

    # Session creations allowed per ip_hash per window, before Stripe is
    # even asked (core.ratelimit).
    CHECKOUT_LIMIT = 8
    CHECKOUT_WINDOW_SECONDS = 10 * 60

    class Meta:
        verbose_name = "Support page"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only for a brand-new, unsaved instance (the blank Add child page
        # form), so an existing page's own values are never touched.
        if not self.pk:
            if not self.slug:
                self.slug = "support"
            if not self.search_description:
                self.search_description = (
                    "Sites of Grace is free for every pilgrim. If it has helped you, you "
                    "can help support its continued growth."
                )

    # --- Validation ---

    def clean(self):
        super().clean()
        errors = {}

        min_amount, max_amount = self.min_amount or 0, self.max_amount or 0
        if min_amount < support.ABSOLUTE_MIN_DOLLARS:
            errors["min_amount"] = "The minimum must be at least $1."
        elif max_amount > support.ABSOLUTE_MAX_DOLLARS:
            errors["max_amount"] = "The maximum can't be more than $1,000."
        elif max_amount <= min_amount:
            errors["max_amount"] = "The maximum must be more than the minimum."

        try:
            presets = support.parse_presets(self.preset_amounts)
        except ValueError as exc:
            errors["preset_amounts"] = str(exc)
            presets = None
        if presets is not None and "min_amount" not in errors and "max_amount" not in errors:
            if not 1 <= len(presets) <= 6:
                errors["preset_amounts"] = "Enter between 1 and 6 amounts."
            elif any(not min_amount <= amount <= max_amount for amount in presets):
                errors["preset_amounts"] = (
                    f"Every amount must be between ${min_amount:,} and ${max_amount:,}."
                )
            else:
                if self.default_amount_once not in presets:
                    errors["default_amount_once"] = "Choose one of the preset amounts."
                if self.allow_monthly and self.default_amount_monthly not in presets:
                    errors["default_amount_monthly"] = "Choose one of the preset amounts."

        if errors:
            raise ValidationError(errors)

    @property
    def preset_list(self):
        try:
            return support.parse_presets(self.preset_amounts)
        except ValueError:
            return []

    @property
    def frequencies(self):
        if self.allow_monthly:
            return (support.FREQUENCY_ONCE, support.FREQUENCY_MONTHLY)
        return (support.FREQUENCY_ONCE,)

    # --- Rendering ---

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        submitted = kwargs.get("support_form") or {}

        frequency = submitted.get("frequency")
        if frequency not in self.frequencies:
            frequency = support.FREQUENCY_ONCE
        custom = submitted.get("custom", "")
        amount = submitted.get("amount") or ""
        if custom:
            amount = "other"
        elif amount != "other" and not (amount.isdigit() and int(amount) in self.preset_list):
            default = (
                self.default_amount_monthly
                if frequency == support.FREQUENCY_MONTHLY
                else self.default_amount_once
            )
            amount = str(default)

        shown = custom.lstrip("$") if amount == "other" else amount
        thanks = kwargs.get("support_thanks")
        context.update({
            # Fills {amount} in the monthly notice; support.js keeps it current.
            "support_amount_label": f"${shown}" if shown else "the amount you choose",
            "support_enabled": settings.SUPPORT_ENABLED,
            "support_frequency": frequency,
            "support_amount": amount,
            "support_custom": custom,
            "support_error": kwargs.get("support_error", ""),
            "support_thanks": thanks,
            "support_range": "${:,} to ${:,}".format(*support.amount_bounds(self)),
            "support_continue_url": _map_or_explore_url() if thanks else "",
        })
        return context

    def serve(self, request, *args, **kwargs):
        if request.method == "POST":
            response = self._serve_checkout(request, *args, **kwargs)
        else:
            thanks = None
            if request.GET.get("thanks") == "1" and settings.SUPPORT_ENABLED:
                thanks = support.completed_session_summary(request.GET.get("session_id", ""))
            response = super().serve(request, *args, support_thanks=thanks, **kwargs)
        # Every render here is per-visitor (a thank-you, an error, the
        # visitor's own choice), so Cloudflare must never cache one.
        response["Cache-Control"] = "private, no-store"
        return response

    def _serve_checkout(self, request, *args, **kwargs):
        frequency = request.POST.get("frequency", "")
        choice = request.POST.get("amount", "")
        custom = request.POST.get("custom_amount", "").strip()[:20]
        submitted = {"frequency": frequency, "amount": choice, "custom": custom}

        def rerender(error=""):
            return Page.serve(
                self, request, *args, support_form=submitted, support_error=error, **kwargs
            )

        if not settings.SUPPORT_ENABLED:
            return rerender()

        if frequency not in self.frequencies:
            return rerender("Please choose how often you'd like to give.")
        try:
            cents = support.amount_to_cents(self, choice, custom)
        except support.AmountError as exc:
            return rerender(str(exc))

        if ratelimit.hit(
            "support-checkout", _ip_hash(request),
            self.CHECKOUT_LIMIT, self.CHECKOUT_WINDOW_SECONDS,
        ):
            return rerender("Please wait a few minutes and try again.")

        try:
            checkout_url = support.create_checkout_session(
                self.get_full_url(request), frequency, cents,
            )
        except stripe.StripeError as exc:
            support.log_stripe_error("Couldn't create a Stripe Checkout Session", exc)
            return rerender(
                "We couldn't reach our payment provider. Please try again in a moment."
            )

        redirect = HttpResponseRedirect(checkout_url)
        redirect.status_code = 303
        return redirect


# --- Contact ------------------------------------------------------------

# The topic cards' icons: the Support set plus the three the Contact mockup
# adds. includes/_line_icon.html has a branch for every value here.
CONTACT_ICON_CHOICES = SUPPORT_ICON_CHOICES + [
    ("question", "Question"),
    ("edit", "Edit"),
    ("partners", "Partners"),
]


class ContactTopicCardBlock(StructBlock):
    topic = ChoiceBlock(choices=contact_models.TOPIC_CHOICES)
    title = CharBlock(max_length=60)
    blurb = TextBlock(required=False)
    icon = ChoiceBlock(choices=CONTACT_ICON_CHOICES)

    class Meta:
        icon = "pick"
        label = "Topic card"


class ContactFaqBlock(StructBlock):
    question = CharBlock(max_length=160)
    answer = RichTextBlock(features=PROSE_FEATURES)

    class Meta:
        icon = "help"
        label = "Question"


class ContactPage(Page):
    """ "Contact Us" -- a real contact form. Messages are saved as
    contact.ContactMessage, read in the admin "Messages" inbox, and alert
    staff by email (contact/notify.py). Nothing is ever emailed to the
    sender.

    Every copy field is prefilled with the mockup's copy as its default= so
    Add child page -> Contact page opens already written. serve() handles
    the form at the page's own URL: POST validates, saves, and redirects to
    ?sent=1, which shows the thank-you once. The contact email isn't a page
    field: the sidebar shows Settings > Legal details' contact email.
    """

    # --- Hero ---
    hero_eyebrow = models.CharField(max_length=60, blank=True, default="Contact Us")
    hero_title = models.CharField(max_length=120, blank=True, default="We'd Love to Hear From You")
    hero_intro = models.TextField(
        blank=True,
        default=(
            "Whether you have a question about a sacred site, a place we should add, a "
            "correction to share, or a prayer you'd like us to carry, every message is read "
            "by a real person."
        ),
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Without one, the hero uses the brand gradient panel.",
    )

    # --- Topic cards ---
    topics_eyebrow = models.CharField(max_length=60, blank=True, default="How Can We Help?")
    topics_heading = models.CharField(max_length=120, blank=True, default="Choose a Topic to Get Started")
    topic_cards = StreamField(
        [("card", ContactTopicCardBlock())],
        max_num=8,
        blank=True,
        help_text="Shortcuts into the form. The form's topic list always offers all eight topics.",
        default=[
            {"type": "card", "value": {
                "topic": "question", "title": "Ask a Question", "icon": "question",
                "blurb": "About a site, a saint, or the Church's teaching.",
            }},
            {"type": "card", "value": {
                "topic": "suggest", "title": "Suggest a Site", "icon": "pin",
                "blurb": "A shrine, miracle, or holy place we're missing.",
            }},
            {"type": "card", "value": {
                "topic": "correction", "title": "Submit a Correction", "icon": "edit",
                "blurb": "Help us keep every page accurate.",
            }},
            {"type": "card", "value": {
                "topic": "pilgrimage", "title": "Plan a Pilgrimage", "icon": "map",
                "blurb": "Group trips, parishes, and travel questions.",
            }},
            {"type": "card", "value": {
                "topic": "partner", "title": "Partnerships & Press", "icon": "partners",
                "blurb": "Shrines, tour operators, media, and collaborations.",
            }},
            {"type": "card", "value": {
                "topic": "prayer", "title": "Prayer Request", "icon": "candle",
                "blurb": "Share an intention. We'll hold it in prayer.",
            }},
        ],
    )

    # --- The form ---
    form_heading = models.CharField(max_length=120, blank=True, default="Send Us a Message")
    form_lede = models.CharField(
        max_length=200, blank=True,
        default="We read every message and usually reply within two or three business days.",
    )
    prayer_note = models.CharField(
        max_length=300, blank=True,
        help_text="Shown above the message box while Prayer request is the topic.",
        default=(
            "Your intention stays private. It is never published, and it is deleted after "
            "90 days. We will remember it in prayer."
        ),
    )
    thank_you_heading = models.CharField(
        max_length=120, blank=True, default="Thank You",
        help_text='The sender\'s first name is added after it: "Thank You, John".',
    )
    thank_you_text = models.TextField(
        blank=True,
        default=(
            "Your message is on its way. We'll reply to the email address you gave us, "
            "usually within two or three business days."
        ),
    )
    prayer_thank_you_text = models.TextField(
        blank=True,
        default=(
            "Your intention has been received, and we will remember it in prayer. It stays "
            "private and is never published."
        ),
    )

    # --- Sidebar ---
    reach_heading = models.CharField(max_length=120, blank=True, default="Other Ways to Reach Us")
    response_time = models.CharField(max_length=120, blank=True, default="Two to three business days")
    based_in = models.CharField(max_length=120, blank=True, default="Southern California")
    visit_card_heading = models.CharField(max_length=120, blank=True, default="Planning a Visit?")
    visit_card_text = models.TextField(
        blank=True,
        default=(
            "For Mass times, confession schedules, or access on a particular day, the shrine "
            "itself is the best source. You'll find its official website and contact details "
            "on each site's page."
        ),
    )
    visit_card_link_label = models.CharField(max_length=60, blank=True, default="Find a sacred site")
    visit_card_link = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. Falls back to the interactive map / Explore hub if left blank.",
    )
    independence_note = RichTextField(
        blank=True,
        features=PROSE_FEATURES,
        default=(
            "<p><b>A note on who we are.</b> Sites of Grace is an independent Catholic "
            "resource. We don't speak on behalf of the Church, any diocese, or any "
            "shrine.</p>"
            "<p>For questions about the sacraments or a personal pastoral matter, please "
            "reach out to your parish priest.</p>"
        ),
    )

    # --- FAQ ---
    faq_eyebrow = models.CharField(max_length=60, blank=True, default="Before You Write")
    faq_heading = models.CharField(max_length=120, blank=True, default="Common Questions")
    faqs = StreamField(
        [("faq", ContactFaqBlock())],
        blank=True,
        default=[
            {"type": "faq", "value": {
                "question": "Can I book a pilgrimage through Sites of Grace?",
                "answer": (
                    "<p>We don't run tours ourselves. Each site page links to trusted "
                    "pilgrimage operators and travel resources, and the Plan Your Visit "
                    "guides cover getting there, where to stay, and what to expect. If "
                    "you're organizing a parish or group trip, send us a message and we'll "
                    "point you in the right direction.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "I found an error on a page. What should I do?",
                "answer": (
                    "<p>Thank you for helping. Choose \"Submit a Correction\" above and link "
                    "the page. Every site and saint page also has a \"Spot an error?\" link "
                    "that fills this in for you. We check every correction against Church "
                    "and shrine sources before we change anything.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "How do you decide which sites to include?",
                "answer": (
                    "<p>We include places of genuine Catholic significance, and we're careful "
                    "to show each one's status as the Church describes it: approved, "
                    "recognized as a devotion, or still under study. Suggestions are always "
                    "welcome.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "Can I share my own photos from a pilgrimage?",
                "answer": (
                    "<p>Yes. Create a free pilgrim account, mark the sites you've visited, "
                    "and add your photos. You choose whether each photo is private or shared "
                    "with other pilgrims.</p>"
                ),
            }},
            {"type": "faq", "value": {
                "question": "What happens to my prayer request?",
                "answer": (
                    "<p>It's read only by the Sites of Grace team and is never published or "
                    "shared. We keep it for 90 days so it can be remembered in prayer, and "
                    "then it's deleted.</p>"
                ),
            }},
        ],
    )

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("hero_eyebrow"),
                FieldPanel("hero_title"),
                FieldPanel("hero_intro"),
                FieldPanel("hero_image"),
            ],
            heading="Hero",
        ),
        MultiFieldPanel(
            [
                FieldPanel("topics_eyebrow"),
                FieldPanel("topics_heading"),
                FieldPanel("topic_cards"),
            ],
            heading="Topic Cards",
        ),
        MultiFieldPanel(
            [
                FieldPanel("form_heading"),
                FieldPanel("form_lede"),
                FieldPanel("prayer_note"),
                FieldPanel("thank_you_heading"),
                FieldPanel("thank_you_text"),
                FieldPanel("prayer_thank_you_text"),
            ],
            heading="Form and Thank-You",
        ),
        MultiFieldPanel(
            [
                FieldPanel("reach_heading"),
                FieldPanel("response_time"),
                FieldPanel("based_in"),
                FieldPanel("visit_card_heading"),
                FieldPanel("visit_card_text"),
                FieldPanel("visit_card_link_label"),
                PageChooserPanel("visit_card_link"),
                FieldPanel("independence_note"),
            ],
            heading="Sidebar",
            help_text=(
                "The email address comes from Settings > Legal details, and the social "
                "links from Settings > Site settings."
            ),
        ),
        MultiFieldPanel(
            [
                FieldPanel("faq_eyebrow"),
                FieldPanel("faq_heading"),
                FieldPanel("faqs"),
            ],
            heading="Common Questions",
        ),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    max_count = 1
    template = "home/contact_page.html"

    # A coarse, per-process flood guard checked before anything else
    # (core.ratelimit). The real limit is RATE_LIMIT below, counted from
    # the ContactMessage table so it holds across gunicorn workers.
    FLOOD_LIMIT = 20
    RATE_LIMIT = 5
    RATE_WINDOW_SECONDS = 60 * 60
    RATE_LIMIT_MESSAGE = (
        "You've sent several messages in a short time. Please try again in a little while."
    )
    SESSION_KEY = "contact_sent"

    class Meta:
        verbose_name = "Contact page"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only for a brand-new, unsaved instance (the blank Add child page
        # form), so an existing page's own values are never touched.
        if not self.pk:
            if not self.slug:
                self.slug = "contact"
            if not self.search_description:
                self.search_description = (
                    "Questions, corrections, site suggestions, and prayer requests. Every "
                    "message to Sites of Grace is read by a real person."
                )

    @property
    def visit_card_url(self):
        if self.visit_card_link_id and self.visit_card_link.live:
            return self.visit_card_link.url
        return _map_or_explore_url()

    # --- Rendering ---

    def _initial(self, request):
        initial = {"topic": contact_models.DEFAULT_TOPIC, "ts": contact_forms.issue_ts()}
        topic = request.GET.get("topic", "")
        if topic in contact_models.TOPIC_KEYS:
            initial["topic"] = topic
        related = contact_forms.allowed_related_page(request.GET.get("page"))
        if related:
            initial["related_page"] = str(related.pk)
        user = request.user
        if user.is_authenticated:
            profile = getattr(user, "pilgrim_profile", None)
            initial["name"] = user.get_full_name() or (profile.display_name if profile else "")
            initial["email"] = user.email
        return initial

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        form = kwargs.get("contact_form") or contact_forms.ContactForm(initial=self._initial(request))

        values = form.data if form.is_bound else form.initial
        topic = values.get("topic", "")
        if topic not in contact_models.TOPIC_KEYS:
            topic = contact_models.DEFAULT_TOPIC
        related = contact_forms.allowed_related_page(values.get("related_page"))

        # (field id, first error) for the summary above the form.
        error_summary = [
            (form[name].id_for_label, errors[0])
            for name, errors in form.errors.items()
            if name in form.fields and not form.fields[name].widget.is_hidden
        ] if form.is_bound else []

        details = LegalDetails.load(request_or_site=request)
        context.update({
            # Root-relative on this request's own site.
            "contact_page_url": self.get_url(request),
            "contact_form": form,
            "contact_topic": topic,
            "contact_topic_copy": contact_models.TOPIC_COPY[topic],
            # contact.js swaps the message label, placeholder, and picker per
            # topic from this (rendered with json_script).
            "contact_copy": {
                key: dict(copy, related=key in contact_models.RELATED_TOPICS)
                for key, copy in contact_models.TOPIC_COPY.items()
            },
            "contact_shows_related": topic in contact_models.RELATED_TOPICS,
            "contact_related": related,
            "contact_error": kwargs.get("contact_error", ""),
            "contact_error_summary": error_summary,
            "contact_thanks": kwargs.get("contact_thanks"),
            "contact_email": details.contact_email,
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY if contact_turnstile.enabled() else "",
        })
        return context

    def serve(self, request, *args, **kwargs):
        if request.method == "POST":
            response = self._serve_post(request, *args, **kwargs)
        else:
            thanks = None
            if request.GET.get("sent") == "1":
                # Shown once: the first name and topic come from the
                # session, never the URL, and are popped on this render.
                thanks = request.session.pop(self.SESSION_KEY, None) or {}
            response = super().serve(request, *args, contact_thanks=thanks, **kwargs)
        # Every render here is per-visitor (a prefilled name, a thank-you,
        # an error), so Cloudflare must never cache one.
        response["Cache-Control"] = "private, no-store"
        return response

    def _serve_post(self, request, *args, **kwargs):
        form = contact_forms.ContactForm(request.POST)
        ip_hash = _ip_hash(request)

        def rerender(error=""):
            return Page.serve(self, request, *args, contact_form=form, contact_error=error, **kwargs)

        if ratelimit.hit("contact-form", ip_hash, self.FLOOD_LIMIT, self.RATE_WINDOW_SECONDS):
            return rerender(self.RATE_LIMIT_MESSAGE)

        # Spam is saved as spam and answered with the normal thank-you, and
        # no email goes out. A bot is never told why.
        if self._looks_like_spam(request.POST):
            message = self._save_spam(request, ip_hash)
            return self._thank_you_redirect(request, message)

        # The real rate limit, counted from saved, non-spam messages.
        recent = contact_models.ContactMessage.objects.filter(
            ip_hash=ip_hash,
            created_at__gte=timezone.now() - timedelta(seconds=self.RATE_WINDOW_SECONDS),
        ).exclude(status=contact_models.ContactMessage.STATUS_SPAM)
        if recent.count() >= self.RATE_LIMIT:
            return rerender(self.RATE_LIMIT_MESSAGE)

        if contact_turnstile.enabled() and not contact_turnstile.verify(
            request.POST.get(contact_forms.TURNSTILE_FIELD, "")
        ):
            return rerender("We couldn't confirm you're not a robot. Please try the check again.")

        if not form.is_valid():
            return rerender()

        data = form.cleaned_data
        message = contact_models.ContactMessage.objects.create(
            topic=data["topic"],
            name=data["name"],
            email=data["email"],
            related_page=data["related_page"],
            message=data["message"],
            user=request.user if request.user.is_authenticated else None,
            ip_hash=ip_hash,
        )
        contact_models.ContactMessage.purge_expired()
        contact_notify.send_staff_alert(message)
        return self._thank_you_redirect(request, message)

    @staticmethod
    def _looks_like_spam(post):
        return (
            bool(post.get(contact_forms.HONEYPOT_FIELD, "").strip())
            or contact_forms.ts_is_suspicious(post.get("ts", ""))
            or contact_forms.too_many_urls(post.get("message", ""))
        )

    @staticmethod
    def _save_spam(request, ip_hash):
        post = request.POST
        topic = post.get("topic", "")
        return contact_models.ContactMessage.objects.create(
            topic=topic if topic in contact_models.TOPIC_KEYS else "other",
            name=" ".join(post.get("name", "").split())[:120],
            email=post.get("email", "").strip()[:254],
            related_page=contact_forms.allowed_related_page(post.get("related_page")),
            message=post.get("message", "")[: contact_models.MESSAGE_MAX_LENGTH],
            status=contact_models.ContactMessage.STATUS_SPAM,
            user=request.user if request.user.is_authenticated else None,
            ip_hash=ip_hash,
        )

    def _thank_you_redirect(self, request, message):
        names = message.name.split()
        request.session[self.SESSION_KEY] = {
            "first_name": names[0] if names else "",
            "prayer": message.is_prayer,
        }
        redirect = HttpResponseRedirect(f"{self.get_url(request)}?sent=1#contact-form")
        redirect.status_code = 303
        return redirect


# --- Legal pages ---------------------------------------------------------------


@register_setting(icon="doc-full")
class LegalDetails(BaseGenericSetting):
    """Who runs the site and the DMCA agent: the values behind the {{TOKENS}}
    in the legal pages and notices (see home/legal.py). Blank by default --
    a LegalPage can't be published while a value it uses is blank."""

    operator_name = models.CharField("Operator name", max_length=200, blank=True)
    contact_email = models.EmailField("Contact email", blank=True)
    mailing_address = models.TextField("Mailing address", blank=True)
    dmca_agent_name = models.CharField("DMCA agent name", max_length=200, blank=True)
    dmca_agent_address = models.TextField("DMCA agent address", blank=True)
    dmca_agent_phone = models.CharField("DMCA agent phone", max_length=40, blank=True)
    dmca_agent_email = models.EmailField("DMCA agent email", blank=True)

    panels = [
        MultiFieldPanel(
            [FieldPanel("operator_name"), FieldPanel("contact_email"), FieldPanel("mailing_address")],
            heading="Operator",
        ),
        MultiFieldPanel(
            [
                FieldPanel("dmca_agent_name"),
                FieldPanel("dmca_agent_address"),
                FieldPanel("dmca_agent_phone"),
                FieldPanel("dmca_agent_email"),
            ],
            heading="Designated copyright (DMCA) agent",
        ),
    ]

    class Meta:
        verbose_name = "Legal details"


@register_setting(icon="info-circle")
class LegalNotices(BaseGenericSetting):
    """The short legal notices shown next to the features they describe.
    **bold** and [text](url) are the only formatting; {{TOKENS}} are filled
    from Legal details, and a link to a legal page appears only once that
    page is live (home/legal.py: render_notice)."""

    footer_independence = models.TextField(
        default=(
            "Sites of Grace is an independent Catholic educational and pilgrimage "
            "resource. Unless expressly stated, it is not affiliated with or endorsed by "
            "the Holy See, a diocese, parish, shrine, or religious community. Church "
            "status information should be checked against official sources. [Catholic "
            "Content Notice](/catholic-content-notice/)"
        ),
        help_text="Footer, bottom row, above the copyright line.",
    )
    footer_newsletter = models.TextField(
        default="Unsubscribe anytime. See our [Privacy Policy](/privacy-policy/).",
        help_text="Footer, small text under the newsletter Sign Up button.",
    )
    signup = models.TextField(
        default=(
            "By creating an account, you agree to the [Terms of Use](/terms-of-use/) and "
            "acknowledge the [Privacy Policy](/privacy-policy/). If you are under 18, "
            "please get permission from a parent or guardian first."
        ),
        help_text="Sign-up form, directly above the Sign Up button.",
    )
    site_travel = models.TextField(
        default=(
            "**Pilgrim travel note:** Mass times, opening hours, costs, accessibility, "
            "and local conditions can change. Please confirm important details directly "
            "with the shrine and your providers before you travel. [Travel "
            "Disclaimer](/travel-disclaimer/)"
        ),
        help_text="Sacred site pages, right after the Plan Your Visit section.",
    )
    plan_estimate = models.TextField(
        default=(
            "**Planning estimate only:** These figures are illustrative and are not a "
            "live price quote. Rates, availability, fees, exchange rates, and conditions "
            "can change. Confirm final costs with each provider before booking. [Travel "
            "Disclaimer](/travel-disclaimer/)"
        ),
        help_text="Trip calculator (/plan/), under the estimated total.",
    )
    tour_links = models.TextField(
        default=(
            "**Affiliate disclosure:** Some pilgrimage-tour links on this page may earn "
            "Sites of Grace a commission if you book through them, at no extra cost to "
            "you. Tours are run by independent providers. Review their itineraries, "
            "payment terms, and cancellation policies before booking. [Affiliate "
            "Disclosure](/affiliate-disclosure/)"
        ),
        help_text="Above tour-operator links. Not shown anywhere yet: no page renders tour-operator links.",
    )
    travel_links = models.TextField(
        default=(
            "**Travel referral notice:** Some travel links on this page may earn Sites of"
            " Grace a commission, at no extra cost to you. Map distances and routes are "
            "approximate; confirm location, accessibility, availability, rates, and "
            "booking terms with the provider. [Affiliate "
            "Disclosure](/affiliate-disclosure/) · [Travel "
            "Disclaimer](/travel-disclaimer/)"
        ),
        help_text="Above travel and hotel booking links. Not shown anywhere yet: the site has no booking links.",
    )
    blog_affiliate = models.TextField(
        default=(
            "**Affiliate disclosure:** This article contains links that may earn Sites of"
            " Grace a commission on qualifying purchases, at no extra cost to you. "
            "[Affiliate Disclosure](/affiliate-disclosure/)"
        ),
        help_text='Blog posts with "Has affiliate links" turned on, above the article.',
    )
    store_amazon = models.TextField(
        default=(
            "**As an Amazon Associate I earn from qualifying purchases.** Prices, "
            "availability, shipping, and returns are set by the seller. [Affiliate "
            "Disclosure](/affiliate-disclosure/)"
        ),
        help_text="Store page, under the intro.",
    )
    store_waitlist = models.TextField(
        default=(
            "Joining the waitlist doesn't place an order or charge you, and it doesn't "
            "sign you up for our newsletter. [Privacy Policy](/privacy-policy/)"
        ),
        help_text="Store, just before each waitlist button.",
    )
    share_rights_checkbox = models.TextField(
        default=(
            "I took this photo or have permission to share it, and anyone recognizable in"
            " it has agreed to be shown. I'm not sharing private information about "
            "children or anyone else. ([Community Policy](/community-policy/))"
        ),
        help_text="Label of the checkbox a pilgrim must tick every time they share a photo publicly.",
    )
    share_adult_checkbox = models.TextField(
        default="I am 18 or older.",
        help_text="Label of the one-time 18+ checkbox for sharing photos publicly or making a profile public.",
    )
    share_public_warning = models.TextField(
        default=(
            "**Public post:** Once shared, your photo, display name, and caption can be "
            "seen by anyone. Leave out private details and locations you don't want "
            "others to see. [Privacy Policy](/privacy-policy/)"
        ),
        help_text="Next to the public-sharing controls on the photo upload and photo pages.",
    )
    profile_public_warning = models.TextField(
        default=(
            "**Public profile:** anyone will be able to see your whole profile, including"
            " your badges and your Visited and Want-to-Go lists, and anyone can follow "
            "you without your approval. [Privacy Policy](/privacy-policy/)"
        ),
        help_text="Profile settings, next to the private profile setting.",
    )
    testimony = models.TextField(
        default=(
            "Personal stories of favors and healing reflect the contributor's own "
            "account. They are not independently verified medical findings or a guarantee"
            " of results, and spiritual practices are not a substitute for medical care. "
            "[Catholic Content Notice](/catholic-content-notice/)"
        ),
        help_text="Under a story or testimony composer. Not shown anywhere yet: the site has none.",
    )
    support_intro = models.TextField(
        default=(
            "**Support is optional.** Sites of Grace is independently operated and is not"
            " a 501(c)(3) charity. Payments are not tax-deductible and do not unlock paid"
            " features. If you choose monthly support, your selected amount is charged "
            "each month until you cancel. [Support & Billing "
            "Notice](/support-and-billing/)"
        ),
        help_text="Support page, above the checkout button.",
    )
    support_monthly = models.TextField(
        default=(
            "You'll be charged {amount} every month until you cancel. Cancel anytime from"
            " Manage monthly support."
        ),
        help_text="Support page, under the frequency choice while Monthly is selected. {amount} is filled in.",
    )
    stripe_monthly_submit = models.TextField(
        default=(
            "By confirming, you authorize Sites of Grace to charge {amount} every month "
            "until you cancel. Cancel anytime from the Manage monthly support link on "
            "sitesofgrace.com/support/."
        ),
        help_text="Stripe's checkout page, above the pay button, for monthly support only. {amount} is filled in. Plain text: bold and links are dropped.",
    )
    contact_legal = models.TextField(
        default=(
            "We use your name and email only to reply to you. We never add you to a "
            "mailing list without asking. See our [Privacy Policy](/privacy-policy/)."
        ),
        help_text="Contact page, under the form next to the Send button.",
    )

    class Meta:
        verbose_name = "Legal notices"


LEGAL_BODY_FEATURES = ["h2", "h3", "bold", "italic", "link", "ol", "ul"]


class LegalPage(Page):
    """One legal page (Privacy Policy, Terms of Use, ...). Made as drafts by
    `manage.py create_legal_pages` from legal/content/*.md.

    The body's {{TOKENS}} are filled from Legal details at render time.
    Publishing is blocked while a value the body uses is blank -- see
    home/wagtail_hooks.py -- and if one is cleared later, it renders as
    nothing (with a warning logged), never as "{{...}}".
    """

    effective_date = models.DateField()
    body = RichTextField(features=LEGAL_BODY_FEATURES)

    content_panels = Page.content_panels + [
        FieldPanel("effective_date"),
        FieldPanel("body"),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = []
    template = "home/legal_page.html"

    class Meta:
        verbose_name = "Legal page"

    def publish_problem(self, details=None):
        """Why this page can't be published yet, or "" if it can."""
        try:
            missing = legal.missing_fields(self.body, details or LegalDetails.load())
        except legal.UnknownTokenError as exc:
            return f"{exc}. Fix the page text before publishing."
        if missing:
            return (
                "This page can't be published until these are filled in under "
                f"Settings > Legal details: {', '.join(missing)}. "
                "Your changes were saved as a draft."
            )
        return ""

    def rendered_body(self, details=None):
        """(html, toc): the body with tokens filled and <h2> ids added."""
        html = expand_db_html(self.body)
        try:
            html = legal.fill_tokens(html, details or LegalDetails.load())
        except legal.UnknownTokenError:
            logger.error("LegalPage %s uses an unknown token; rendering without it.", self.pk)
            html = legal.TOKEN_RE.sub("", html)
        return legal.add_heading_ids(html)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["legal_body"], context["legal_toc"] = self.rendered_body(
            LegalDetails.load(request_or_site=request)
        )
        return context
