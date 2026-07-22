"""
Site-wide settings for Sites of Grace.

These fields power the footer, social links, contact block, newsletter copy,
and the site-wide trust disclaimer. Because this is a BaseSiteSetting, an editor
can change everything here from the Wagtail admin (Settings > Site settings)
without touching code, and the values are available in every template via the
`settings` context processor, e.g.  {{ settings.core.SiteSettings.tagline }}
"""
from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting


@register_setting
class SiteSettings(BaseSiteSetting):
    # --- Brand ---
    logo = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Header/footer logo. Leave blank to fall back to the text wordmark.",
    )
    tagline = models.CharField(
        max_length=180,
        blank=True,
        default="Discover the sacred places where heaven has touched earth.",
    )
    footer_summary = models.TextField(
        blank=True,
        default=(
            "Sites of Grace is a Catholic pilgrimage and sacred-sites reference: "
            "explore Marian apparitions, Eucharistic miracles, saints' tombs, "
            "shrines, and Holy Land destinations around the world."
        ),
    )

    # --- Social ---
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True, verbose_name="X (Twitter) URL")

    # --- Contact ---
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)

    # --- Newsletter ---
    newsletter_heading = models.CharField(
        max_length=120, blank=True, default="Stay inspired on your journey."
    )
    newsletter_text = models.CharField(
        max_length=240,
        blank=True,
        default="Receive sacred site spotlights, Catholic teaching, pilgrimage ideas, and prayers each week.",
    )

    # --- Trust / legal ---
    disclaimer = models.TextField(
        blank=True,
        default=(
            "Sites of Grace is an independent educational Catholic resource and does "
            "not speak officially on behalf of the Catholic Church, any diocese, "
            "shrine, or religious community. Church status information should be "
            "verified through official diocesan or Vatican sources whenever possible."
        ),
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("logo"), FieldPanel("tagline"), FieldPanel("footer_summary")],
            heading="Brand",
        ),
        MultiFieldPanel(
            [
                FieldPanel("facebook_url"),
                FieldPanel("instagram_url"),
                FieldPanel("youtube_url"),
                FieldPanel("x_url"),
            ],
            heading="Social links",
        ),
        MultiFieldPanel(
            [FieldPanel("contact_email"), FieldPanel("contact_phone")],
            heading="Contact",
        ),
        MultiFieldPanel(
            [FieldPanel("newsletter_heading"), FieldPanel("newsletter_text")],
            heading="Newsletter",
        ),
        FieldPanel("disclaimer"),
    ]

    class Meta:
        verbose_name = "Site settings"


class NewsletterSignup(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email
