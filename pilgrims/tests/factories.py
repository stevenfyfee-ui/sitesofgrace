"""Small in-memory fixture builders shared across the pilgrims test package.

Builds real, decodable JPEG bytes with Pillow directly — no extra test-only
dependency (piexif etc.) — so imaging.py is exercised against genuine EXIF
data, including a real embedded GPS IFD.
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

ORIENTATION_TAG = 0x0112
GPS_IFD_TAG = 0x8825

_SAMPLE_GPS_IFD = {
    1: "N",
    2: (IFDRational(40, 1), IFDRational(44, 1), IFDRational(0, 1)),
    3: "W",
    4: (IFDRational(73, 1), IFDRational(59, 1), IFDRational(0, 1)),
}


def make_jpeg_bytes(*, width=800, height=600, color=(200, 50, 50), with_gps=False,
                     orientation=None):
    image = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()

    if with_gps or orientation:
        exif = image.getexif()
        if orientation:
            exif[ORIENTATION_TAG] = orientation
        if with_gps:
            exif[GPS_IFD_TAG] = _SAMPLE_GPS_IFD
        image.save(buf, format="JPEG", exif=exif)
    else:
        image.save(buf, format="JPEG")
    return buf.getvalue()


def make_uploaded_jpeg(name="photo.jpg", **kwargs):
    data = make_jpeg_bytes(**kwargs)
    return SimpleUploadedFile(name, data, content_type="image/jpeg")


def make_uploaded_fake_image(name="fake.jpg"):
    """A non-image renamed to look like a jpeg — must be rejected by decoded
    format, not filename/Content-Type."""
    return SimpleUploadedFile(name, b"this is definitely not a jpeg", content_type="image/jpeg")


def grant_wagtail_admin_access(user):
    """is_staff (Django's own flag, which our own permissions/views check)
    is NOT enough to reach any /admin/ URL — Wagtail wraps every
    admin urlpattern, including hook-registered ones like the moderation
    queue, in require_admin_access(), which checks the separate
    wagtailadmin.access_admin permission. Grant that too for any test user
    that needs to actually load a moderation admin view (function-level
    permission tests like staff_can_view_reported_photo don't need this —
    only client.get()/post() against the /admin/... URLs do)."""
    from django.contrib.auth.models import Permission

    permission = Permission.objects.get(codename="access_admin", content_type__app_label="wagtailadmin")
    user.user_permissions.add(permission)


def verify_email(user):
    """User.objects.create_user() (used throughout these tests) doesn't go
    through allauth's signup flow, so it leaves no EmailAddress row at all —
    exactly the gap permissions.can_comment()'s verified-email check exists
    to catch. Call this for any test user that should be able to comment."""
    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=user, email=user.email, defaults={"verified": True, "primary": True}
    )
