from django.contrib.auth import get_user_model
from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import PilgrimPhoto, PilgrimProfile, Post, PostPhoto, RESERVED_HANDLES

PHOTO_FILE_FIELDS = ("original", "large", "feed", "thumb", "public_large", "public_thumb")


def generate_unique_handle(user):
    """A slug-safe, unique, non-reserved starting handle.

    Derived from the email local-part (allauth accounts are email-first, so
    `username` is often a random string, not something a pilgrim chose).
    Settings lets them change it later.
    """
    base = slugify((user.email or user.get_username() or "pilgrim").split("@")[0])[:26] or "pilgrim"
    if base in RESERVED_HANDLES:
        base = f"{base}-pilgrim"

    handle = base
    suffix = 1
    while handle in RESERVED_HANDLES or PilgrimProfile.objects.filter(handle=handle).exists():
        suffix += 1
        handle = f"{base}{suffix}"[:30]
    return handle


@receiver(post_save, sender=get_user_model())
def create_pilgrim_profile(sender, instance, created, **kwargs):
    if not created:
        return
    PilgrimProfile.objects.get_or_create(
        user=instance, defaults={"handle": generate_unique_handle(instance)}
    )


@receiver(post_delete, sender=PilgrimPhoto)
def delete_pilgrim_photo_files(sender, instance, **kwargs):
    """Fires for both instance.delete() and queryset.delete() (bulk delete
    sends post_delete per row too), so bulk-delete in the album view can't
    leave orphaned objects in Spaces."""
    for field_name in PHOTO_FILE_FIELDS:
        field_file = getattr(instance, field_name)
        if field_file:
            field_file.storage.delete(field_file.name)


@receiver(post_delete, sender=PostPhoto)
def decrement_post_photo_count(sender, instance, **kwargs):
    """Post.photo_count is denormalized and post_compose is not the only
    way a PostPhoto row can disappear — deleting a PilgrimPhoto from the
    phase-2 library/album views CASCADEs into this table too (Django sends
    post_delete for cascade-deleted rows same as a direct delete), which
    would otherwise leave photo_count stale without this."""
    Post.objects.filter(pk=instance.post_id).update(photo_count=F("photo_count") - 1)
