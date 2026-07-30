from django.db import models
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page
from wagtail.snippets.models import register_snippet
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

CATEGORY_CHOICES = [
    ("Books", "Books"),
    ("Films", "Films"),
    ("Devotionals & Sacramentals", "Devotionals & Sacramentals"),
    ("Clothing", "Clothing"),
    ("Gifts", "Gifts"),
]

KIND_CHOICES = [
    ("affiliate", "Affiliate (Amazon / external)"),
    ("own", "Our own product"),
]


@register_snippet
class StoreProduct(models.Model):
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
    ]

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    @property
    def is_affiliate(self):
        return self.kind == "affiliate"

    @property
    def show_price(self):
        return self.kind == "own" and bool(self.price)

    @property
    def cta_label(self):
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
        context["products"] = products
        context["store_settings"] = StoreSettings.objects.first()
        return context
