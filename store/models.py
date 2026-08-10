from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.models import Orderable, Page
from wagtail.snippets.models import register_snippet
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

CATEGORY_CHOICES = [
    ("Books", "Books"),
    ("Films", "Films"),
    ("Devotionals & Sacramentals", "Devotionals & Sacramentals"),
    ("Clothing", "Clothing"),
    ("Gifts", "Gifts"),
    ("Subscriptions", "Subscriptions"),
    ("Calendars & Planners", "Calendars & Planners"),
]

KIND_CHOICES = [
    ("affiliate", "Affiliate (Amazon / external)"),
    ("own", "Our own product"),
]

LAYOUT_CHOICES = [
    ("card", "Card (grid)"),
    ("feature", "Feature (full-width)"),
]

CTA_MODE_CHOICES = [
    ("link", "Link (Link URL / Amazon)"),
    ("waitlist", "Waitlist (collects an email, no payment)"),
]


@register_snippet
class StoreProduct(ClusterableModel):
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True, help_text="Author, artist, or brand")
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="affiliate")
    description = models.TextField(blank=True)
    image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    amazon_asin = models.CharField(
        max_length=20, blank=True,
        help_text="Amazon ASIN (e.g. B0XXXXXXX). Builds a tagged affiliate link.",
    )
    link_url = models.URLField(
        blank=True,
        help_text="Used when there's no ASIN: an external affiliate URL, or the "
                  "checkout URL for our own products.",
    )
    price = models.CharField(
        max_length=20, blank=True,
        help_text="Only shown for our own products, e.g. $24.99. Leave blank for "
                  "Amazon items (price shows on Amazon).",
    )
    featured = models.BooleanField(default=False, help_text="Show on the homepage band.")
    sort_order = models.IntegerField(default=0)
    live = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    layout = models.CharField(max_length=10, choices=LAYOUT_CHOICES, default="card")
    long_description = RichTextField(blank=True, help_text="Shown only in feature layout.")
    ribbon_text = models.CharField(
        max_length=60, blank=True, help_text='e.g. "Quarterly Subscription", "New for 2027"',
    )
    spotlight_title = models.CharField(
        max_length=120, blank=True, help_text='e.g. "Autumn 2026 · Lourdes, France"',
    )
    spotlight_note = models.CharField(
        max_length=120, blank=True, help_text='e.g. "Shipping the first week of October"',
    )
    fine_print = models.CharField(
        max_length=300, blank=True, help_text="Shipping and renewal terms shown under the buttons.",
    )
    cta_mode = models.CharField(
        max_length=10, choices=CTA_MODE_CHOICES, default="link",
        help_text="Waitlist collects an email instead of linking out -- no payment is taken.",
    )

    panels = [
        FieldPanel("title"),
        FieldPanel("subtitle"),
        FieldPanel("category"),
        FieldPanel("kind"),
        FieldPanel("description"),
        FieldPanel("image"),
        FieldPanel("amazon_asin"),
        FieldPanel("link_url"),
        FieldPanel("price"),
        FieldPanel("featured"),
        FieldPanel("sort_order"),
        FieldPanel("live"),
        MultiFieldPanel(
            [
                FieldPanel("layout"),
                FieldPanel("ribbon_text"),
                FieldPanel("long_description"),
                FieldPanel("spotlight_title"),
                FieldPanel("spotlight_note"),
                FieldPanel("fine_print"),
                FieldPanel("cta_mode"),
                InlinePanel("inclusions", label="Inclusion"),
                InlinePanel("price_options", label="Price option"),
            ],
            heading="Feature layout",
        ),
    ]

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    @property
    def is_affiliate(self):
        return self.kind == "affiliate"

    @property
    def is_feature(self):
        return self.layout == "feature"

    @property
    def show_price(self):
        return self.kind == "own" and bool(self.price)

    @property
    def default_price_option(self):
        return self.price_options.filter(is_default=True).first() or self.price_options.first()

    @property
    def cta_label(self):
        if self.cta_mode == "waitlist":
            return "Join the Waitlist"
        if self.kind == "own":
            return "Buy"
        return "View on Amazon" if self.amazon_asin else "View item"

    def get_url(self):
        if self.amazon_asin:
            s = StoreSettings.objects.first()
            tag = s.amazon_associate_tag if s else ""
            base = "https://www.amazon.com/dp/%s/" % self.amazon_asin
            return "%s?tag=%s" % (base, tag) if tag else base
        return self.link_url


class ProductInclusion(Orderable):
    product = ParentalKey(StoreProduct, on_delete=models.CASCADE, related_name="inclusions")
    lead_in = models.CharField(max_length=60, blank=True, help_text="Bolded opening phrase, e.g. \"A blessed rosary\"")
    text = models.CharField(max_length=200)

    panels = [FieldPanel("lead_in"), FieldPanel("text")]


class ProductPriceOption(Orderable):
    product = ParentalKey(StoreProduct, on_delete=models.CASCADE, related_name="price_options")
    label = models.CharField(max_length=60, help_text='e.g. "Full Year · 4 boxes"')
    amount = models.CharField(max_length=20, help_text='e.g. "$196"')
    unit = models.CharField(max_length=20, blank=True, help_text='e.g. "/yr"')
    note = models.CharField(max_length=60, blank=True, help_text='e.g. "Save $20"')
    is_default = models.BooleanField(default=False)

    panels = [
        FieldPanel("label"),
        FieldPanel("amount"),
        FieldPanel("unit"),
        FieldPanel("note"),
        FieldPanel("is_default"),
    ]


class WaitlistSignup(models.Model):
    product = models.ForeignKey(StoreProduct, on_delete=models.CASCADE, related_name="waitlist_signups")
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("product", "email")]

    def __str__(self):
        return f"{self.email} → {self.product}"


@register_setting
class StoreSettings(BaseGenericSetting):
    amazon_associate_tag = models.CharField(max_length=60, blank=True)
    affiliate_disclosure = RichTextField(
        blank=True,
        default="<p>As an Amazon Associate, we earn from qualifying purchases.</p>",
    )
    store_intro = RichTextField(blank=True)

    panels = [
        FieldPanel("amazon_associate_tag"),
        FieldPanel("affiliate_disclosure"),
        FieldPanel("store_intro"),
    ]

    class Meta:
        verbose_name = "Store settings"


class StoreIndexPage(Page):
    heading = models.CharField(max_length=200, blank=True)
    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("heading"),
        FieldPanel("intro"),
    ]
    max_count = 1

    def get_context(self, request):
        context = super().get_context(request)
        from store.models import StoreProduct, StoreSettings, CATEGORY_CHOICES
        valid = {v for v, _ in CATEGORY_CHOICES}
        selected = request.GET.get("category", "")
        products = StoreProduct.objects.filter(live=True)
        if selected in valid:
            products = products.filter(category=selected)
        else:
            selected = ""
        context["categories"] = [v for v, _ in CATEGORY_CHOICES]
        context["selected_category"] = selected
        context["feature_products"] = products.filter(layout="feature").prefetch_related(
            "inclusions", "price_options"
        )
        context["products"] = products.filter(layout="card")
        context["store_settings"] = StoreSettings.objects.first()
        return context
