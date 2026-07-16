"""
LearnPage — a reusable teaching-article page for the Learn library.

One flexible page type used by every Learn topic (Pilgrimage, Mary, the Eucharist,
Saints, ...). Each page is a hero (title + italic lede) followed by an editable,
reorderable list of section blocks (optional icon, heading, long-form rich text,
optional link), and an optional closing call-to-action band.

Icons are optional — leave them blank and a styled placeholder frame shows until
image files are added later.
"""
from django.db import models
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel, PageChooserPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable, Page


class LearnPage(Page):
    lede = models.TextField(
        blank=True,
        help_text="Short italic introduction shown under the title.",
    )

    # Closing call-to-action band (optional)
    closing_heading = models.CharField(max_length=120, blank=True)
    closing_text = models.CharField(max_length=255, blank=True)
    closing_cta_text = models.CharField(max_length=40, blank=True)
    closing_cta_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    closing_cta_url = models.CharField(
        max_length=255, blank=True, help_text="Used only if no page is chosen."
    )

    content_panels = Page.content_panels + [
        FieldPanel("lede"),
        InlinePanel("sections", heading="Sections", label="Section"),
        MultiFieldPanel(
            [
                FieldPanel("closing_heading"),
                FieldPanel("closing_text"),
                FieldPanel("closing_cta_text"),
                PageChooserPanel("closing_cta_page"),
                FieldPanel("closing_cta_url"),
            ],
            heading="Closing band (optional)",
        ),
    ]

    class Meta:
        verbose_name = "Learn page"


class LearnSection(Orderable):
    page = ParentalKey(LearnPage, on_delete=models.CASCADE, related_name="sections")
    icon = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Optional. A styled placeholder shows until an icon is added.",
    )
    heading = models.CharField(max_length=160)
    body = RichTextField(blank=True)
    link_text = models.CharField(max_length=80, blank=True)
    link_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    link_url = models.CharField(
        max_length=255, blank=True, help_text="Used only if no page is chosen."
    )

    panels = [
        FieldPanel("icon"),
        FieldPanel("heading"),
        FieldPanel("body"),
        FieldPanel("link_text"),
        PageChooserPanel("link_page"),
        FieldPanel("link_url"),
    ]
