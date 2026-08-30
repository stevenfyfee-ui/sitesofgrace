"""
Pilgrim Portal — account and profile foundation (phase 1 of 5).

Later phases add photos, a feed, comments, public galleries, and messages.
The models here are shaped so those phases attach cleanly:
  - SiteVisit is where photos will hang (phase 2).
  - Follow/Block and the permissions module are the gate every later view
    (feed, galleries, messages) will call through.
  - Badge/AwardedBadge is a display slot only; nothing awards a badge yet.

Absorbs the former `community` app (PilgrimProfile, JourneyEntry) — see
migration 0003_migrate_from_community for the one-time data copy, and
0002_seed_badges for the three placeholder Badge snippets.
"""
import uuid

from django.conf import settings
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet


# Handles that would collide with a real route or read as an official/system
# account. Built from urls.py's top-level path segments plus the project's
# own reserved words. Keep in sync with sitesofgrace/urls.py.
RESERVED_HANDLES = {
    # from sitesofgrace/urls.py top-level prefixes
    "health", "django-admin", "admin", "documents", "search",
    "newsletter", "store", "accounts", "journey", "passport", "pilgrims",
    # this app's own sub-paths, reserved defensively even though handles
    # live under /pilgrims/u/<handle>/ rather than at these exact segments
    "u", "settings", "requests", "following", "followers",
    # project-wide reserved words called out in the spec
    "staff", "api", "sites", "news", "support", "help", "about",
}


class PilgrimProfile(models.Model):
    DM_POLICY_FOLLOWERS = "followers"
    DM_POLICY_EVERYONE = "everyone"
    DM_POLICY_NOBODY = "nobody"
    DM_POLICY_CHOICES = [
        (DM_POLICY_FOLLOWERS, "Followers I approve"),
        (DM_POLICY_EVERYONE, "Everyone"),
        (DM_POLICY_NOBODY, "No one"),
    ]

    CREDIT_DISPLAY_NAME = "display_name"
    CREDIT_FIRST_NAME_ONLY = "first_name_only"
    CREDIT_ANONYMOUS = "anonymous"
    CREDIT_CHOICES = [
        (CREDIT_DISPLAY_NAME, "My display name"),
        (CREDIT_FIRST_NAME_ONLY, "First name only"),
        (CREDIT_ANONYMOUS, "Anonymous"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pilgrim"
    )
    handle = models.SlugField(
        max_length=30,
        unique=True,
        help_text="Lowercase, used in your profile URL: /pilgrims/u/<handle>/",
    )
    display_name = models.CharField(max_length=60, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    # TODO(phase 2+): move to the private/signed storage backend once it
    # exists — avatars are low-sensitivity but should still not sit on the
    # public-read Spaces bucket alongside marketing assets. Plain ImageField
    # on default storage for now.
    avatar = models.ImageField(upload_to="pilgrims/avatars/", null=True, blank=True)
    home_city = models.CharField(max_length=120, blank=True)
    home_country = models.CharField(max_length=120, blank=True)
    is_private = models.BooleanField(default=True)
    dm_policy = models.CharField(
        max_length=20, choices=DM_POLICY_CHOICES, default=DM_POLICY_FOLLOWERS
    )
    public_credit_default = models.CharField(
        max_length=20, choices=CREDIT_CHOICES, default=CREDIT_DISPLAY_NAME
    )
    age_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pilgrim profile"

    def __str__(self):
        return self.display_name or self.handle

    @property
    def visibility_label(self):
        return "Private" if self.is_private else "Public"


class Follow(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
    ]

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following_set"
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follower_set"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
            models.CheckConstraint(
                condition=~models.Q(follower=models.F("following")),
                name="follow_no_self_follow",
            ),
        ]
        indexes = [
            models.Index(fields=["following", "status"]),
            models.Index(fields=["follower", "status"]),
        ]

    def __str__(self):
        return f"{self.follower} -> {self.following} ({self.status})"


class Block(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_made"
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_received"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(
                condition=~models.Q(blocker=models.F("blocked")),
                name="block_no_self_block",
            ),
        ]

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"


class SiteVisit(models.Model):
    STATUS_VISITED = "visited"
    STATUS_WANT_TO_GO = "want_to_go"
    STATUS_CHOICES = [
        (STATUS_VISITED, "Visited"),
        (STATUS_WANT_TO_GO, "Want to go"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="site_visits"
    )
    site = models.ForeignKey(
        "catalog.SacredSitePage", on_delete=models.CASCADE, related_name="pilgrim_visits"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES)
    visited_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "site"], name="unique_site_visit"),
        ]

    def __str__(self):
        return f"{self.owner} - {self.site} ({self.status})"


@register_snippet
class Badge(models.Model):
    TIER_BRONZE = "bronze"
    TIER_SILVER = "silver"
    TIER_GOLD = "gold"
    TIER_CHOICES = [
        (TIER_BRONZE, "Bronze"),
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
    ]

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, default=TIER_BRONZE)
    sort_order = models.IntegerField(default=0)

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("icon"),
        FieldPanel("tier"),
        FieldPanel("sort_order"),
    ]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Badge"

    def __str__(self):
        return self.name


class AwardedBadge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="awarded_badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awards")
    awarded_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="unique_awarded_badge"),
        ]

    def __str__(self):
        return f"{self.user} — {self.badge}"
