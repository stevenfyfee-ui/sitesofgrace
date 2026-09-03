"""
Single source of truth for who can see and interact with whom.

Every later phase (feed, photos, galleries, messages) calls through these
helpers rather than re-deriving visibility rules in a view. A blocked
relationship overrides everything except the profile owner's own access.
"""
from .models import Block, Follow


def _is_blocked_either_way(user_a, user_b):
    if not (getattr(user_a, "is_authenticated", False) and getattr(user_b, "is_authenticated", False)):
        return False
    return Block.objects.filter(blocker=user_a, blocked=user_b).exists() or (
        Block.objects.filter(blocker=user_b, blocked=user_a).exists()
    )


def is_following(viewer, owner) -> bool:
    """True only for an ACCEPTED follow from viewer to owner."""
    if not getattr(viewer, "is_authenticated", False):
        return False
    return Follow.objects.filter(
        follower=viewer, following=owner, status=Follow.STATUS_ACCEPTED
    ).exists()


def can_view_profile_detail(viewer, owner) -> bool:
    """Full profile (vs. the stub) — self, or public/followed and not blocked."""
    if getattr(viewer, "is_authenticated", False) and viewer.pk == owner.pk:
        return True
    if _is_blocked_either_way(viewer, owner):
        return False
    profile = getattr(owner, "pilgrim", None)
    if profile is None or not profile.is_private:
        return True
    return is_following(viewer, owner)


def can_interact(viewer, owner) -> bool:
    """False if either side has blocked the other. Self is always fine."""
    if getattr(viewer, "is_authenticated", False) and viewer.pk == owner.pk:
        return True
    return not _is_blocked_either_way(viewer, owner)


def accepted_following_ids(user):
    """User ids the given user follows, accepted only. Feeds off this in phase 3."""
    return Follow.objects.filter(
        follower=user, status=Follow.STATUS_ACCEPTED
    ).values_list("following_id", flat=True)


def can_view_photo(viewer, photo) -> bool:
    """Owner-only, for a BARE photo not attached to any post (the
    /pilgrims/photos/<uuid>/ detail view, and the library/album views).
    A photo embedded in a Post is a different question — see
    can_view_post below, which is what feed/post_detail views gate on."""
    return getattr(viewer, "is_authenticated", False) and viewer.pk == photo.owner_id


def can_view_post(viewer, post) -> bool:
    """Owner, or an accepted follower, and not blocked. No other audience —
    see pilgrims/models.py:Post for why there's no visibility field to
    check instead."""
    if getattr(viewer, "is_authenticated", False) and viewer.pk == post.owner_id:
        return True
    if _is_blocked_either_way(viewer, post.owner):
        return False
    return is_following(viewer, post.owner)


def can_comment(viewer, post) -> bool:
    """can_view_post, plus the commenter must be logged in with a verified
    email. In practice every logged-in account already has one —
    ACCOUNT_EMAIL_VERIFICATION="mandatory" blocks login otherwise — so the
    real teeth here are for an account created outside that flow (e.g.
    `manage.py createsuperuser`, which has no allauth EmailAddress row at
    all). Staff gets no bypass here either, consistent with the rest of
    this module."""
    if not getattr(viewer, "is_authenticated", False):
        return False
    if not can_view_post(viewer, post):
        return False
    from allauth.account.models import EmailAddress

    return EmailAddress.objects.filter(user=viewer, verified=True).exists()


def visible_posts_for(viewer):
    """The feed queryset. ONE query for the posts themselves plus one each
    for the two prefetches, regardless of how many posts come back — see
    pilgrims/tests/test_feed.py:test_feed_query_count_does_not_scale."""
    from django.db.models import Prefetch

    from .models import Comment, Post, PostPhoto

    if not getattr(viewer, "is_authenticated", False):
        return Post.objects.none()

    owner_ids = set(accepted_following_ids(viewer))
    owner_ids.add(viewer.pk)
    blocked_ids = set(Block.objects.filter(blocker=viewer).values_list("blocked_id", flat=True))
    blocked_ids |= set(Block.objects.filter(blocked=viewer).values_list("blocker_id", flat=True))
    owner_ids -= blocked_ids

    preview_comments = (
        Comment.objects.filter(parent__isnull=True, is_deleted=False)
        .select_related("author", "author__pilgrim")
        .order_by("created_at")
    )

    return (
        Post.objects.filter(owner_id__in=owner_ids)
        .select_related("owner", "owner__pilgrim", "site")
        .prefetch_related(
            Prefetch(
                "post_photos",
                queryset=PostPhoto.objects.select_related("photo").order_by("sort_order"),
            ),
            Prefetch("comments", queryset=preview_comments[:3], to_attr="preview_comments"),
        )
    )


def can_share_photo(viewer, photo) -> bool:
    """Owner, with a verified email, whose sharing privilege hasn't been
    suspended by staff. Doesn't check whether it's already shared — the
    view decides what "share" vs. "unshare" means for the current state."""
    if not getattr(viewer, "is_authenticated", False):
        return False
    if viewer.pk != photo.owner_id:
        return False
    profile = getattr(viewer, "pilgrim", None)
    if profile is None or not profile.can_share_publicly:
        return False
    from allauth.account.models import EmailAddress

    return EmailAddress.objects.filter(user=viewer, verified=True).exists()


def staff_can_view_reported_photo(staff_user, photo) -> bool:
    """The ONE deliberate exception to "staff get no bypass" established in
    can_view_profile_detail/can_view_post/can_view_photo above: a staff
    member may view a specific photo THAT HAS AN OPEN REPORT against it,
    through the moderation view only — not the owner's other photos, not
    their feed, not their profile.

    Every grant writes a ModerationAction row BEFORE returning True, so
    this bypass can never be exercised silently — including a staff member
    just looking, not yet acting."""
    if not (getattr(staff_user, "is_authenticated", False) and staff_user.is_staff):
        return False

    from .models import ModerationAction, PhotoReport

    if not PhotoReport.objects.filter(photo=photo, status=PhotoReport.STATUS_OPEN).exists():
        return False

    ModerationAction.objects.create(
        actor=staff_user,
        action=ModerationAction.ACTION_VIEW_REPORTED_PHOTO,
        photo=photo,
        owner_affected=photo.owner,
        note="Viewed via the moderation queue.",
    )
    return True
