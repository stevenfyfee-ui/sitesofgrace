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
from django.db import models
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, PageChooserPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page

from catalog.models import (
    CATEGORY_STYLES,
    DEFAULT_CATEGORY_STYLE,
    TRAIL_COLORS,
    PilgrimageTrailPage,
    SacredSitePage,
    SaintPage,
)

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
    # Replaces the old store bucket on the right of the pilgrim band.
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
                FieldPanel("subscription_heading"),
                FieldPanel("subscription_title"),
                FieldPanel("subscription_intro"),
                FieldPanel("subscription_image"),
                InlinePanel("subscription_bullets", label="Bullet", max_num=4),
                FieldPanel("subscription_price_line"),
                FieldPanel("subscription_product"),
                FieldPanel("subscription_cta_text"),
                FieldPanel("subscription_cta_link"),
            ],
            heading="Subscription bucket",
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
    ]

    max_count = 1
    subpage_types = ["home.MapPage", "home.StandardPage", "home.StorePage"]

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

        return context


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
