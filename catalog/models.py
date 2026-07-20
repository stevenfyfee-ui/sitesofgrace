from django.db import models
from modelcluster.fields import ParentalManyToManyField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet

CATEGORY_CHOICES = [
    ("Marian Apparition", "Marian Apparition"),
    ("Eucharistic Miracle", "Eucharistic Miracle"),
    ("Saints & Tombs", "Saints & Tombs"),
    ("Holy Land", "Holy Land"),
    ("Shrine & Basilica", "Shrine & Basilica"),
]

MAP_PAGE_SLUG = "interactive-map"

CANONICAL_STATUS_CHOICES = [
    ("Nihil obstat", "Nihil obstat"),
    ("Prae oculis habeatur", "Prae oculis habeatur"),
    ("Curatur", "Curatur"),
    ("Sub mandato", "Sub mandato"),
    ("Prohibetur", "Prohibetur"),
    ("Declaratio de non supernaturalitate", "Declaratio de non supernaturalitate"),
    ("Not Applicable", "Not Applicable"),
    ("Recognized Devotion", "Recognized Devotion"),
    ("Constat de supernaturalitate (legacy)", "Constat de supernaturalitate (legacy)"),
]


@register_snippet
class Topic(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
    ]

    def __str__(self):
        return self.name


class SaintPage(Page):
    also_known_as = models.CharField(max_length=255, blank=True)
    honorific_type = models.CharField(max_length=255, blank=True)
    feast_day = models.CharField(max_length=120, blank=True)
    born = models.CharField(max_length=160, blank=True)
    died = models.CharField(max_length=160, blank=True)
    canonized = models.CharField(max_length=200, blank=True)
    patronage = models.TextField(blank=True)
    significance = models.TextField(blank=True)
    body = RichTextField(blank=True)
    portrait = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    topics = ParentalManyToManyField("catalog.Topic", blank=True, related_name="saints")
    source_url = models.URLField(blank=True)
    source_note = models.CharField(max_length=255, blank=True)
    data_status = models.CharField(max_length=40, blank=True)
    editor_notes = models.TextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("portrait"),
        MultiFieldPanel(
            [
                FieldPanel("also_known_as"),
                FieldPanel("honorific_type"),
                FieldPanel("feast_day"),
                FieldPanel("born"),
                FieldPanel("died"),
                FieldPanel("canonized"),
            ],
            heading="Identity",
        ),
        FieldPanel("patronage"),
        FieldPanel("significance"),
        FieldPanel("body"),
        FieldPanel("topics"),
        MultiFieldPanel(
            [
                FieldPanel("source_url"),
                FieldPanel("source_note"),
                FieldPanel("data_status"),
                FieldPanel("editor_notes"),
            ],
            heading="Editorial (internal)",
        ),
    ]


class SacredSitePage(Page):
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    canonical_status = models.CharField(max_length=60, blank=True, choices=CANONICAL_STATUS_CHOICES)
    locality = models.CharField(max_length=160, blank=True)
    country = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    date_display = models.CharField(max_length=160, blank=True)
    feast_day = models.CharField(max_length=120, blank=True)
    summary_short = models.TextField(blank=True)
    the_story = RichTextField(blank=True)
    church_recognition = RichTextField(blank=True)
    catholic_teaching = RichTextField(blank=True)
    pilgrimage_info = RichTextField(blank=True)
    go_deeper = RichTextField(blank=True)
    associated_saint = models.ForeignKey(
        "catalog.SaintPage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sites",
    )
    featured_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    topics = ParentalManyToManyField("catalog.Topic", blank=True, related_name="sites")
    location_link = models.URLField(blank=True)
    notes_internal = models.TextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("featured_image"),
        MultiFieldPanel(
            [
                FieldPanel("category"),
                FieldPanel("canonical_status"),
                FieldPanel("locality"),
                FieldPanel("country"),
                FieldPanel("latitude"),
                FieldPanel("longitude"),
                FieldPanel("location_link"),
            ],
            heading="Location",
        ),
        MultiFieldPanel(
            [
                FieldPanel("date_display"),
                FieldPanel("feast_day"),
                FieldPanel("associated_saint"),
                FieldPanel("topics"),
            ],
            heading="Identity",
        ),
        FieldPanel("summary_short"),
        FieldPanel("the_story"),
        FieldPanel("church_recognition"),
        FieldPanel("catholic_teaching"),
        FieldPanel("pilgrimage_info"),
        FieldPanel("go_deeper"),
        FieldPanel("notes_internal"),
    ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["map_page"] = Page.objects.filter(slug=MAP_PAGE_SLUG).first()
        return context
