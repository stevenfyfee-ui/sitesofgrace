from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

from .models import PilgrimProfile, RESERVED_HANDLES


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
