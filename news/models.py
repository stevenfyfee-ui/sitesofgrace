from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

TOPIC_CHOICES = [
    ("shrines", "Shrines & Sites"),
    ("events", "Events & Festivals"),
    ("pilgrimage", "Pilgrimage"),
    ("saints", "Saints & Causes"),
    ("general", "General"),
]


@register_snippet
class NewsSource(models.Model):
    name = models.CharField(max_length=120)
    feed_url = models.URLField()
    enabled = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    last_fetched = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("feed_url"),
        FieldPanel("enabled"),
        FieldPanel("sort_order"),
        FieldPanel("last_fetched", read_only=True),
        FieldPanel("last_error", read_only=True),
    ]

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class NewsItem(models.Model):
    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=300)
    excerpt = models.TextField(help_text="Hard-truncated to ~200 chars at a word boundary by the fetcher.")
    link = models.URLField(max_length=500)
    guid = models.CharField(
        max_length=500, unique=True,
        help_text="Dedupe key from the feed's <guid>, falling back to the link.",
    )
    published_at = models.DateTimeField(db_index=True)
    image_url = models.URLField(
        max_length=500, blank=True, help_text="Only set when the feed supplies a media/enclosure URL.",
    )
    topic = models.CharField(max_length=20, choices=TOPIC_CHOICES, default="general")
    hidden = models.BooleanField(default=False, help_text="Suppress this item from the site without deleting it.")
    fetched_at = models.DateTimeField(auto_now_add=True)

    panels = [
        FieldPanel("source"),
        FieldPanel("title"),
        FieldPanel("excerpt"),
        FieldPanel("link"),
        FieldPanel("published_at"),
        FieldPanel("image_url"),
        FieldPanel("topic"),
        FieldPanel("hidden"),
    ]

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title


class NewsItemViewSet(SnippetViewSet):
    model = NewsItem
    icon = "doc-full"
    menu_label = "News items"
    list_display = ["title", "source", "topic", "published_at", "hidden"]
    list_filter = ["source", "topic", "hidden"]
    search_fields = ["title", "excerpt"]


register_snippet(NewsItemViewSet)
