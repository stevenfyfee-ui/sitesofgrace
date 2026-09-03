"""
Public sharing: the one place private-bucket bytes cross into the public,
CDN-fronted bucket (and back out again on unshare/hide).

pilgrim_private and "default" have DIFFERENT credentials, each scoped to
its own bucket — neither key can touch the other's bucket, so there is no
server-side S3 CopyObject shortcut here. Every share/unshare/hide/unhide
below reads bytes out of one storage and writes them into the other
through the app process. Do not "optimize" this into a CopyObject call —
it will fail with AccessDenied, and that failure is correct: it means the
keys are scoped the way they're supposed to be.
"""
from django.core.files.base import ContentFile
from django.utils import timezone

from . import imaging

GALLERY_STORAGE_PREFIX = "pilgrim-gallery"


def _write_public_copies(photo):
    """Reads large/thumb from pilgrim_private, strips EXIF, re-encodes, and
    writes the result into the default (public) storage."""
    with photo.large.open("rb") as f:
        large_bytes = imaging.strip_all_exif_jpeg(f.read())
    with photo.thumb.open("rb") as f:
        thumb_bytes = imaging.strip_all_exif_jpeg(f.read())

    base = f"{GALLERY_STORAGE_PREFIX}/{photo.uuid}"
    photo.public_large.save(f"{base}/large.jpg", ContentFile(large_bytes), save=False)
    photo.public_thumb.save(f"{base}/thumb.jpg", ContentFile(thumb_bytes), save=False)


def _delete_public_copies(photo):
    if photo.public_large:
        photo.public_large.delete(save=False)
    if photo.public_thumb:
        photo.public_thumb.delete(save=False)


def share_photo(photo, *, credit):
    """Owner-initiated: publish to the site gallery."""
    _write_public_copies(photo)
    photo.is_public_on_site = True
    photo.public_shared_at = timezone.now()
    photo.public_credit = credit
    photo.save(update_fields=[
        "public_large", "public_thumb", "is_public_on_site", "public_shared_at", "public_credit",
    ])


def unshare_photo(photo):
    """Owner-initiated: full withdrawal. Distinct from hide_photo — this
    clears is_public_on_site too, so an unhide later has nothing to
    restore (there's no longer an active share to reinstate)."""
    _delete_public_copies(photo)
    photo.is_public_on_site = False
    photo.public_shared_at = None
    photo.public_credit = ""
    photo.save(update_fields=[
        "public_large", "public_thumb", "is_public_on_site", "public_shared_at", "public_credit",
    ])


def hide_photo(photo, *, reason):
    """Staff/auto-hide: suppress without touching is_public_on_site — the
    owner's share is still "on" underneath, just not currently public. A
    cached CDN URL must not keep serving the image after this, so the
    public objects are deleted, not just filtered out of the gallery
    query."""
    if photo.hidden_by_staff:
        return
    _delete_public_copies(photo)
    photo.hidden_by_staff = True
    photo.hidden_reason = reason
    photo.hidden_at = timezone.now()
    photo.save(update_fields=[
        "public_large", "public_thumb", "hidden_by_staff", "hidden_reason", "hidden_at",
    ])


def unhide_photo(photo):
    """Deliberate staff action only. Regenerates the public copies from the
    still-private originals IF the owner's share is still active; if the
    owner separately unshared it in the meantime, there's nothing to
    restore — just clear the hidden flags."""
    if photo.is_public_on_site:
        _write_public_copies(photo)
    photo.hidden_by_staff = False
    photo.hidden_reason = ""
    photo.hidden_at = None
    photo.save(update_fields=[
        "public_large", "public_thumb", "hidden_by_staff", "hidden_reason", "hidden_at",
    ])
