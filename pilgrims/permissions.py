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
    """Owner-only in phase 2 — no feed, no follower sharing, no public
    sharing yet. Routed through here (rather than a bare `==` check in the
    view) so phase 3/4 only need to widen this one function."""
    return getattr(viewer, "is_authenticated", False) and viewer.pk == photo.owner_id
