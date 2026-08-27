from django.db import models
from django.db.models import Count, Q
from django.utils.text import slugify
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.models import Orderable, Page
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting

# The buckets the store shipped with. These are only used to seed the
# ProductCategory table the first time migrations run -- after that, categories
# are edited in the admin under Store -> Categories, not here.
DEFAULT_CATEGORIES = [
    "Books",
    "Films",
    "Devotionals & Sacramentals",
    "Clothing",
    "Gifts",
    "Subscriptions",
    "Calendars & Planners",
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


class ProductCategory(models.Model):
    """A store bucket. Add, rename, reorder, or hide these in the admin."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(
        max_length=60, unique=True, blank=True,
        help_text="Used in the ?category= link. Leave blank and it is generated from the name.",
    )
    description = models.CharField(
        max_length=200, blank=True,
        help_text="Optional internal note. Not shown on the site.",
    )
    sort_order = models.IntegerField(
        default=0, help_text="Lower numbers appear first in the filter row.",
    )
    live = models.BooleanField(
        default=True,
        help_text="Uncheck to take this bucket and everything in it off the store page, "
                  "without deleting anything.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("sort_order"),
        FieldPanel("live"),
        FieldPanel("description"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "product category"
        verbose_name_plural = "product categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:56] or "category"
            slug = base
            n = 2
            while ProductCategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = "%s-%d" % (base, n)
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def product_count(self):
        return self.products.filter(live=True).count()

    product_count.short_description = "Live products"


class StoreProduct(ClusterableModel):
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True, help_text="Author, artist, or brand")
    category = models.ForeignKey(
        ProductCategory, null=True, on_delete=models.SET_NULL, related_name="products",
        help_text="Which bucket this shows up under on the store page.",
    )
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
    live = models.BooleanField(default=True, help_text="Uncheck to take this off the store page.")
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
        MultiFieldPanel(
            [
                FieldPanel("title"),
                FieldPanel("subtitle"),
                FieldPanel("category"),
                FieldPanel("kind"),
                FieldPanel("description"),
                FieldPanel("image"),
            ],
            heading="The basics",
        ),
        MultiFieldPanel(
            [
                FieldPanel("amazon_asin"),
                FieldPanel("link_url"),
                FieldPanel("price"),
            ],
            heading="Where it links and what it costs",
        ),
        MultiFieldPanel(
            [
                FieldPanel("live"),
                FieldPanel("featured"),
                FieldPanel("sort_order"),
                FieldPanel("layout"),
            ],
            heading="Placement",
        ),
        MultiFieldPanel(
            [
                FieldPanel("ribbon_text"),
                FieldPanel("long_description"),
                FieldPanel("spotlight_title"),
                FieldPanel("spotlight_note"),
                FieldPanel("fine_print"),
                FieldPanel("cta_mode"),
                InlinePanel("inclusions", label="Inclusion"),
                InlinePanel("price_options", label="Price option"),
            ],
            heading="Feature layout extras",
            classname="collapsed",
        ),
    ]

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def admin_thumb(self):
        if not self.image:
            return ""
        try:
            from django.utils.html import format_html

            rendition = self.image.get_rendition("fill-50x50")
            return format_html(
                '<img src="{}" width="50" height="50" alt="" '
                'style="border-radius:4px;object-fit:cover;">',
                rendition.url,
            )
        except Exception:
            return ""

    admin_thumb.short_description = ""

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

    panels = [FieldPanel("product"), FieldPanel("email")]

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


def store_listing_context(request):
    """Everything the store listing template needs.

    Shared by store.StoreIndexPage and home.StorePage so the product grid
    renders no matter which page type is sitting at /store/.
    """
    categories = list(
        ProductCategory.objects.filter(live=True)
        .annotate(n_live=Count("products", filter=Q(products__live=True)))
        .filter(n_live__gt=0)
    )
    by_slug = {c.slug: c for c in categories}

    selected = (request.GET.get("category") or "").strip()
    if selected and selected not in by_slug:
        # Tolerate the old ?category=Books links, which used the name.
        match = next((c for c in categories if c.name.lower() == selected.lower()), None)
        selected = match.slug if match else ""

    # A hidden category takes its products off the store page with it. Products
    # whose category was deleted outright stay visible, just without a bucket.
    products = (
        StoreProduct.objects.filter(live=True)
        .filter(Q(category__live=True) | Q(category__isnull=True))
        .select_related("category")
    )
    if selected:
        products = products.filter(category__slug=selected)

    return {
        "categories": categories,
        "selected_category": selected,
        "feature_products": products.filter(layout="feature").prefetch_related(
            "inclusions", "price_options"
        ),
        "products": products.filter(layout="card"),
        "store_settings": StoreSettings.objects.first(),
    }


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
        context.update(store_listing_context(request))
        return context
