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
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.snippets.models import register_snippet

from .storage import get_pilgrim_private_storage


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
            # Backs the follow-request rate limit's
            # filter(follower=X, created_at__gte=Y) — neither index above
            # has created_at, so without this Postgres can only prefix-seek
            # to this follower's rows and scan them for the date filter.
            models.Index(fields=["follower", "created_at"]),
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


class PilgrimPhoto(models.Model):
    """A pilgrim's own photo of a sacred site.

    Private by default (phase 2 scope): only `original`/`large`/`feed`/
    `thumb` on the `pilgrim_private` storage are used. The `public_*` /
    `is_public_on_site` / `hidden_*` fields are declared now so phase 4
    (public sharing) doesn't need a second migration on a table that will
    already hold rows — nothing sets or reads them yet.

    An album is never a model — it's just
    PilgrimPhoto.objects.filter(owner=..., site=...).
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="photos"
    )
    # PROTECT: an editor deleting or unpublishing a SacredSitePage in the
    # Wagtail admin must never silently destroy a pilgrim's photos. See
    # pilgrims/wagtail_hooks.py for the admin-side guard that turns the
    # resulting ProtectedError into a clear editor-facing message instead of
    # a 500.
    site = models.ForeignKey(
        "catalog.SacredSitePage", on_delete=models.PROTECT, related_name="pilgrim_photos"
    )
    caption = models.CharField(max_length=300, blank=True)
    taken_on = models.DateField(null=True, blank=True)

    # Private storage (pilgrim_private) — see sitesofgrace/settings/base.py
    # and pilgrims/storage.py (why this can't just be storage="pilgrim_private").
    original = models.FileField(storage=get_pilgrim_private_storage, max_length=255)
    large = models.ImageField(storage=get_pilgrim_private_storage, max_length=255)
    feed = models.ImageField(storage=get_pilgrim_private_storage, max_length=255)
    thumb = models.ImageField(storage=get_pilgrim_private_storage, max_length=255)

    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    byte_size = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)  # sha256 hex, duplicate detection

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Public-share fields: unused until phase 4 ---
    is_public_on_site = models.BooleanField(default=False)
    public_shared_at = models.DateTimeField(null=True, blank=True)
    public_credit = models.CharField(
        max_length=20, choices=PilgrimProfile.CREDIT_CHOICES, blank=True
    )
    # No storage= given -> Django's own default_storage (the CDN-fronted
    # public bucket). Only ever populated once a photo is actually shared
    # publicly, in phase 4.
    public_large = models.ImageField(null=True, blank=True)
    public_thumb = models.ImageField(null=True, blank=True)
    hidden_by_staff = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=255, blank=True)
    hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-taken_on", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "site"]),
            models.Index(fields=["site", "is_public_on_site", "hidden_by_staff"]),
            # Backs the upload rate limit's
            # filter(owner=X, created_at__gte=Y) — (owner, site) doesn't
            # cover a created_at range scan.
            models.Index(fields=["owner", "created_at"]),
        ]

    def __str__(self):
        return f"{self.owner} — {self.site} ({self.uuid})"

    @classmethod
    def create_from_processed(cls, *, owner, site, processed, caption="", taken_on=None):
        """processed: an imaging.ProcessedPhoto. Writes all four private
        derivatives to storage and saves the row in one call."""
        photo = cls(
            owner=owner,
            site=site,
            caption=caption,
            taken_on=taken_on,
            width=processed.width,
            height=processed.height,
            byte_size=processed.byte_size,
            content_hash=processed.content_hash,
        )
        base = f"pilgrims/{owner.pilgrim.uuid}/{photo.uuid}"
        photo.original.save(
            f"{base}/original.{processed.original_ext}",
            ContentFile(processed.original_bytes),
            save=False,
        )
        photo.large.save(f"{base}/large.jpg", ContentFile(processed.large_bytes), save=False)
        photo.feed.save(f"{base}/feed.jpg", ContentFile(processed.feed_bytes), save=False)
        photo.thumb.save(f"{base}/thumb.jpg", ContentFile(processed.thumb_bytes), save=False)
        photo.save()
        return photo


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


class Post(models.Model):
    """Visible to the owner and their ACCEPTED followers — full stop.

    No visibility field: there is only one audience for a post, so nothing
    to store. photo_count/comment_count are denormalized counters kept in
    sync by the views that create/delete PostPhoto/Comment rows (there's no
    signal for this — see pilgrims/views.py — since the counters only ever
    change through those same few code paths).
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts"
    )
    # PROTECT + null=True: a post doesn't have to be about one specific
    # site, but if it is, deleting that SacredSitePage must not silently
    # destroy the post (same reasoning as PilgrimPhoto.site).
    site = models.ForeignKey(
        "catalog.SacredSitePage", null=True, blank=True,
        on_delete=models.PROTECT, related_name="pilgrim_posts",
    )
    caption = models.TextField(max_length=2000, blank=True)
    photo_count = models.PositiveIntegerField(default=0)
    comment_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "created_at"]),
        ]

    def __str__(self):
        return f"Post by {self.owner} ({self.uuid})"


class PostPhoto(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="post_photos")
    photo = models.ForeignKey(PilgrimPhoto, on_delete=models.CASCADE, related_name="post_photos")
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["post", "photo"], name="unique_post_photo"),
        ]

    def clean(self):
        if self.photo_id and self.post_id and self.photo.owner_id != self.post.owner_id:
            raise ValidationError("A post can only include photos owned by the same pilgrim.")

    def __str__(self):
        return f"{self.photo} in {self.post}"


class Comment(models.Model):
    """Attaches to a Post and ONLY a Post (never a bare photo) — deliberate:
    it's what makes it structurally impossible to comment on a photo once
    it's shared to a public site page in phase 4. `photo`, when set, scopes
    the comment to one photo within the post rather than the post overall.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    photo = models.ForeignKey(
        PilgrimPhoto, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    # Soft delete: a thread with a hole in it still makes sense; one with a
    # row physically gone does not. Render "comment removed" instead.
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["post", "created_at"]),
            # Backs the comment rate limit's
            # filter(author=X, created_at__gte=Y) — the (post, created_at)
            # index above doesn't have author as a leading column, so this
            # query would otherwise fall back to the plain single-column
            # index Django creates for the author FK by default.
            models.Index(fields=["author", "created_at"]),
        ]

    def clean(self):
        if self.parent_id and self.parent.parent_id:
            raise ValidationError("Replies are one level deep only — can't reply to a reply.")
        if self.photo_id and self.post_id and not self.post.post_photos.filter(photo_id=self.photo_id).exists():
            raise ValidationError("That photo isn't part of this post.")

    def __str__(self):
        return f"Comment by {self.author} on {self.post}"


class Notification(models.Model):
    VERB_FOLLOW_REQUEST = "follow_request"
    VERB_FOLLOW_ACCEPTED = "follow_accepted"
    VERB_COMMENT_ON_POST = "comment_on_post"
    VERB_COMMENT_REPLY = "comment_reply"
    VERB_CHOICES = [
        (VERB_FOLLOW_REQUEST, "New follower request"),
        (VERB_FOLLOW_ACCEPTED, "Follow approved"),
        (VERB_COMMENT_ON_POST, "Comment on your post"),
        (VERB_COMMENT_REPLY, "Reply to your comment"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    verb = models.CharField(max_length=20, choices=VERB_CHOICES)
    # Not a ForeignKey on purpose: the target is a different model per verb
    # (PilgrimProfile.uuid for the two follow verbs, Post.uuid for the two
    # comment verbs) and there are only ever two of those, so a
    # GenericForeignKey would be more machinery than the two-way dispatch in
    # get_target_url() below.
    target_uuid = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
        ]

    def __str__(self):
        return f"{self.get_verb_display()} for {self.recipient}"

    def get_target_url(self):
        from django.urls import reverse

        if self.verb in (self.VERB_FOLLOW_REQUEST, self.VERB_FOLLOW_ACCEPTED):
            profile = PilgrimProfile.objects.filter(uuid=self.target_uuid).first()
            if profile is None:
                return None
            return reverse("pilgrims:profile_detail", args=[profile.handle])
        post = Post.objects.filter(uuid=self.target_uuid).first()
        if post is None:
            return None
        return reverse("pilgrims:post_detail", args=[post.uuid])
