"""
The blog: one editor-managed BlogIndexPage (at /blog/) holding BlogPostPages.

Every list of posts on the site -- the index, a category page, the RSS feed,
previous/next, "More in ..." -- comes from blog_posts(), so the newest-first
ordering and the live/public filter are written exactly once.
"""
import datetime
import math

from django import forms
from django.contrib.syndication.views import Feed
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.http import Http404
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.html import strip_tags
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from wagtail import blocks
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import FieldPanel, InlinePanel, PageChooserPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, path
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Orderable, Page
from wagtail.rich_text import RichText
from wagtail.search import index
from wagtail.snippets.models import register_snippet

WORDS_PER_MINUTE = 220
FEED_ITEM_COUNT = 20
MORE_IN_CATEGORY_COUNT = 3


def blog_posts():
    """Every live, public post, newest first by its editorial date.

    first_published_at breaks ties so two posts dated the same day keep a
    stable order (the later-published one first).
    """
    return (
        BlogPostPage.objects.live().public()
        .order_by("-date", "-first_published_at")
        .prefetch_related("categories")
        .select_related("feature_image")
    )


@register_snippet
class BlogCategory(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)
    description = models.TextField(
        blank=True, help_text="Shown under the heading on this category's page."
    )
    sort_order = models.IntegerField(
        default=0, help_text="Lower numbers come first in the category chips."
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Blog category"
        verbose_name_plural = "Blog categories"

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Body blocks
# ---------------------------------------------------------------------------

class HeadingBlock(blocks.CharBlock):
    class Meta:
        icon = "title"
        template = "blog/blocks/heading.html"


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    caption = blocks.CharBlock(required=False)
    width = blocks.ChoiceBlock(
        choices=[("column", "Column width"), ("wide", "Wide")],
        default="column",
    )

    class Meta:
        icon = "image"
        template = "blog/blocks/image.html"


class QuoteBlock(blocks.StructBlock):
    text = blocks.TextBlock()
    attribution = blocks.CharBlock(required=False)

    class Meta:
        icon = "openquote"
        template = "blog/blocks/quote.html"


class CalloutBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    text = blocks.RichTextBlock(features=["bold", "italic", "link", "ol", "ul"])

    class Meta:
        icon = "warning"
        template = "blog/blocks/callout.html"


class SiteLinkBlock(blocks.StructBlock):
    """The bridge from a post back to the map: a compact card for one sacred
    site or saint page."""
    page = blocks.PageChooserBlock(page_type=["catalog.SacredSitePage", "catalog.SaintPage"])
    note = blocks.CharBlock(required=False)

    class Meta:
        icon = "site"
        template = "blog/blocks/site_link.html"
        label = "Site or saint link"

    def get_context(self, value, parent_context=None):
        from catalog.models import SaintPage

        context = super().get_context(value, parent_context=parent_context)
        target = value["page"].specific if value["page"] else None
        context["target"] = target if target and target.live else None
        context["is_saint"] = isinstance(target, SaintPage)
        return context


BODY_BLOCKS = [
    ("heading", HeadingBlock()),
    ("paragraph", blocks.RichTextBlock(
        features=["bold", "italic", "link", "ol", "ul", "h3", "blockquote"],
        template="blog/blocks/paragraph.html",
    )),
    ("image", ImageBlock()),
    ("quote", QuoteBlock()),
    ("embed", EmbedBlock(icon="media", template="blog/blocks/embed.html")),
    ("callout", CalloutBlock()),
    ("site_link", SiteLinkBlock()),
]


def _block_text(value):
    """All the reader-visible words in one stream block value, as plain text."""
    if isinstance(value, RichText):
        return strip_tags(value.source)
    if isinstance(value, str):
        return value
    if isinstance(value, blocks.StructValue):
        return " ".join(_block_text(v) for k, v in value.items() if k != "width")
    return ""


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

class BlogIndexPage(RoutablePageMixin, Page):
    eyebrow = models.CharField(max_length=60, default="From the Pilgrim's Desk")
    intro = models.TextField(
        default=(
            "Stories of sacred places, practical pilgrimage travel guides, and the "
            "saints who made these places holy."
        ),
    )
    posts_per_page = models.PositiveSmallIntegerField(default=12)

    content_panels = Page.content_panels + [
        FieldPanel("eyebrow"),
        FieldPanel("intro"),
        FieldPanel("posts_per_page"),
    ]

    parent_page_types = ["home.HomePage"]
    subpage_types = ["blog.BlogPostPage"]
    max_count = 1
    template = "blog/blog_index_page.html"

    class Meta:
        verbose_name = "Blog index page"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.pk and not self.slug:
            self.slug = "blog"

    def category_url(self, slug):
        return self.url + self.reverse_subpage("category", kwargs={"slug": slug})

    @property
    def feed_url(self):
        return self.url + self.reverse_subpage("feed")

    def get_context(self, request, *args, category=None, **kwargs):
        context = super().get_context(request, *args, **kwargs)

        posts = blog_posts().child_of(self)
        if category:
            posts = posts.filter(categories=category)

        # The newest post is pulled out as the featured card and kept out of
        # the paginated grid entirely, so it never appears twice and page 2
        # doesn't skip the post that page 1's grid would otherwise have ended on.
        featured_post = posts.first()
        rest = posts.exclude(pk=featured_post.pk) if featured_post else posts

        paginator = Paginator(rest, self.posts_per_page or 12)
        try:
            page_obj = paginator.page(request.GET.get("page", 1))
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)

        # A category's chip is hidden while it has no live posts (except the
        # one being viewed, so its empty state still has a highlighted chip).
        with_posts = set(
            blog_posts().child_of(self).prefetch_related(None).values_list("categories", flat=True)
        )
        categories = []
        for cat in BlogCategory.objects.all():
            cat.url = self.category_url(cat.slug)
            cat.is_active = category is not None and cat.pk == category.pk
            cat.has_posts = cat.pk in with_posts
            categories.append(cat)

        context.update({
            "page_obj": page_obj,
            "posts": page_obj.object_list,
            "active_category": category,
            "categories": categories,
            "featured_post": featured_post if page_obj.number == 1 else None,
            "has_any_posts": featured_post is not None,
            "feed_url": self.feed_url,
        })
        return context

    @path("")
    def index_route(self, request, *args, **kwargs):
        return self.render(request)

    @path("category/<slug:slug>/", name="category")
    def category_route(self, request, slug):
        try:
            category = BlogCategory.objects.get(slug=slug)
        except BlogCategory.DoesNotExist:
            raise Http404("No such blog category")
        return self.render(request, category=category)

    @path("feed/", name="feed")
    def feed_route(self, request):
        return BlogFeed(self)(request)


class BlogFeed(Feed):
    """RSS 2.0 for one blog index. Every link is absolute (page.full_url) --
    django.contrib.sites' domain isn't kept in step with the real host, so
    Feed's own add_domain() can't be trusted to build them."""
    feed_type = Rss201rev2Feed

    def __init__(self, index_page):
        super().__init__()
        self.index_page = index_page

    def __call__(self, request, *args, **kwargs):
        self.request = request
        return super().__call__(request, *args, **kwargs)

    def title(self):
        return "Sites of Grace Blog"

    def link(self):
        return self.index_page.get_full_url(self.request)

    def feed_url(self):
        return self.link() + self.index_page.reverse_subpage("feed")

    def description(self):
        return self.index_page.intro

    def items(self):
        return blog_posts().child_of(self.index_page)[:FEED_ITEM_COUNT]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.excerpt

    def item_link(self, item):
        return item.get_full_url(self.request)

    def item_guid(self, item):
        return item.get_full_url(self.request)

    def item_pubdate(self, item):
        return timezone.make_aware(datetime.datetime.combine(item.date, datetime.time()))

    def item_categories(self, item):
        return [c.name for c in item.sorted_categories]


NO_CATEGORY_ERROR = "Choose at least one category for this post."


class BlogPostPageForm(WagtailAdminPageForm):
    """Requires at least one category.

    The check lives on the form, not in BlogPostPage.clean(): Django validates
    the model before it assigns many-to-many values from the form, so in the
    admin a model-level check would always see an empty category list and
    reject every post, ticked boxes or not.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories"].error_messages["required"] = NO_CATEGORY_ERROR

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("categories") and "categories" not in self.errors:
            self.add_error("categories", NO_CATEGORY_ERROR)
        return cleaned_data


class BlogPostPage(Page):
    date = models.DateField(
        default=datetime.date.today,
        help_text="Shown on the post. Posts are ordered newest first by this date.",
    )
    author_name = models.CharField(max_length=80, default="Steven Fyffe")
    excerpt = models.TextField(
        max_length=300,
        help_text=(
            "One or two sentences. Used on blog cards, in search results, and as "
            "the description in link previews."
        ),
    )
    feature_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    categories = ParentalManyToManyField(BlogCategory, blank=False, related_name="posts")
    body = StreamField(BODY_BLOCKS, blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("author_name"),
        FieldPanel("categories", widget=forms.CheckboxSelectMultiple),
        FieldPanel("excerpt"),
        FieldPanel("feature_image"),
        FieldPanel("body"),
        InlinePanel("related_pages", label="Related places & saints", max_num=3),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("excerpt"),
        index.SearchField("body"),
        index.RelatedFields("categories", [index.SearchField("name")]),
    ]

    base_form_class = BlogPostPageForm
    parent_page_types = ["blog.BlogIndexPage"]
    subpage_types = []
    template = "blog/blog_post_page.html"

    class Meta:
        verbose_name = "Blog post"

    @property
    def reading_time(self):
        words = sum(len(_block_text(block.value).split()) for block in self.body)
        return max(1, math.ceil(words / WORDS_PER_MINUTE))

    @property
    def sorted_categories(self):
        return sorted(self.categories.all(), key=lambda c: (c.sort_order, c.name))

    @property
    def meta_description(self):
        return self.search_description or self.excerpt

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        index_page = self.get_parent().specific
        siblings = blog_posts().child_of(index_page)

        category_links = [
            {"name": c.name, "url": index_page.category_url(c.slug)}
            for c in self.sorted_categories
        ]
        first_category = self.sorted_categories[0] if self.sorted_categories else None
        more_posts = (
            list(siblings.filter(categories=first_category).exclude(pk=self.pk)[:MORE_IN_CATEGORY_COUNT])
            if first_category else []
        )

        # Previous/next by the same date ordering the index uses. Done in
        # Python over the ordered id list so the tie-break on
        # first_published_at can't drift from blog_posts().
        ordered_ids = list(siblings.prefetch_related(None).values_list("pk", flat=True))
        newer_post = older_post = None
        if self.pk in ordered_ids:
            i = ordered_ids.index(self.pk)
            if i > 0:
                newer_post = siblings.get(pk=ordered_ids[i - 1])
            if i + 1 < len(ordered_ids):
                older_post = siblings.get(pk=ordered_ids[i + 1])

        related = [
            r.target.specific for r in self.related_pages.select_related("target")
            if r.target and r.target.live
        ]

        context.update({
            "index_page": index_page,
            "category_links": category_links,
            "first_category": first_category,
            "more_posts": more_posts,
            "newer_post": newer_post,
            "older_post": older_post,
            "related": related,
        })
        return context


class BlogPostRelatedPage(Orderable):
    post = ParentalKey(BlogPostPage, on_delete=models.CASCADE, related_name="related_pages")
    target = models.ForeignKey(
        "wagtailcore.Page", on_delete=models.CASCADE, related_name="+",
        verbose_name="Place, saint, or trail",
    )

    panels = [
        PageChooserPanel(
            "target",
            ["catalog.SacredSitePage", "catalog.SaintPage", "catalog.PilgrimageTrailPage"],
        ),
    ]
