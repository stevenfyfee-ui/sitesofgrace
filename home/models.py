"""
Page models for the site skeleton.

Deliberately lean — these are the structural pages that hang the nav and the
page tree together. Content models (SitePage, SaintPage, RoutePage, the category
listing/filter logic, etc.) come in later passes; nothing here forecloses them.
"""
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page


class HomePage(Page):
    hero_heading = models.CharField(
        max_length=120,
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
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    primary_cta_text = models.CharField(max_length=40, blank=True, default="Explore the Map")
    primary_cta_link = models.CharField(max_length=255, blank=True, default="/interactive-map/")
    secondary_cta_text = models.CharField(max_length=40, blank=True, default="Begin Your Journey")
    secondary_cta_link = models.CharField(max_length=255, blank=True, default="#")

    content_panels = Page.content_panels + [
        FieldPanel("hero_heading"),
        FieldPanel("hero_intro"),
        FieldPanel("hero_image"),
        FieldPanel("primary_cta_text"),
        FieldPanel("primary_cta_link"),
        FieldPanel("secondary_cta_text"),
        FieldPanel("secondary_cta_link"),
    ]

    max_count = 1
    subpage_types = ["home.MapPage", "home.StandardPage", "home.StorePage"]

    class Meta:
        verbose_name = "Home page"


class StandardPage(Page):
    intro = models.TextField(blank=True)
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Standard page"


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
    intro = models.TextField(
        blank=True,
        default="Prayer resources, study guides, and pilgrimage keepsakes — coming soon.",
    )
    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "Store page"