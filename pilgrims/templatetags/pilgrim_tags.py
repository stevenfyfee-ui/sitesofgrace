"""
Presigned-URL access to private pilgrim photos.

This tag does NOT check permissions — it assumes the calling VIEW already
ran the photo through permissions.can_view_photo OR can_view_post (or an
owner-only queryset filter) before the template ever renders. A private
object's URL is only ever generated here, never hardcoded or cached across
viewers, since S3Storage.url() with querystring_auth=True mints a fresh,
time-boxed signature on every call.
"""
from django import template

from pilgrims.models import Notification

register = template.Library()

ALLOWED_SIZES = {"original", "large", "feed", "thumb", "public_large", "public_thumb"}


@register.simple_tag
def pilgrim_photo_url(photo, size):
    if size not in ALLOWED_SIZES:
        return ""
    field = getattr(photo, size, None)
    if not field:
        return ""
    return field.url


@register.simple_tag
def unread_notification_count(user):
    if not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()
