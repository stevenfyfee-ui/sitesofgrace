"""
Public sharing (phase 4): the private/public bucket crossing, the auto-hide
policy, reporting, and the moderation queue. Overrides BOTH "pilgrim_private"
and "default" storage to local temp directories — real credentials for
either bucket aren't available in this environment, and using the real
"default" storage would otherwise write test files into the actual dev
MEDIA_ROOT.
"""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .. import imaging, moderation, sharing
from ..models import Follow, ModerationAction, PhotoReport, PilgrimPhoto
from ..permissions import can_share_photo, staff_can_view_reported_photo
from .factories import make_uploaded_jpeg, verify_email
from .test_photos import _make_site


class _PublicAndPrivateStorageTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._private_dir = tempfile.mkdtemp(prefix="pilgrim_private_test_")
        cls._public_dir = tempfile.mkdtemp(prefix="pilgrim_public_test_")
        from django.conf import settings as dj_settings

        storages = dict(dj_settings.STORAGES)
        storages["pilgrim_private"] = {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": cls._private_dir, "base_url": "/private-test/"},
        }
        storages["default"] = {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": cls._public_dir, "base_url": "/public-test/"},
        }
        cls._override = override_settings(STORAGES=storages)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._private_dir, ignore_errors=True)
        shutil.rmtree(cls._public_dir, ignore_errors=True)
        super().tearDownClass()


def _make_photo(owner, site, **kwargs):
    processed = imaging.process_upload(make_uploaded_jpeg(**kwargs))
    return PilgrimPhoto.create_from_processed(owner=owner, site=site, processed=processed)


class ShareUnshareTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("share_owner", "share_owner@example.com", "pw")
        verify_email(self.owner)
        self.site = _make_site()
        self.photo = _make_photo(self.owner, self.site)
        self.client = Client()
        self.client.force_login(self.owner)

    def test_share_creates_public_objects(self):
        response = self.client.post(
            reverse("pilgrims:photo_share", args=[self.photo.uuid]), {"credit": "display_name"}
        )
        self.assertTrue(response.json()["success"])
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.is_public_on_site)
        self.assertIsNotNone(self.photo.public_shared_at)
        self.assertEqual(self.photo.public_credit, "display_name")
        self.assertTrue(self.photo.public_large.storage.exists(self.photo.public_large.name))
        self.assertTrue(self.photo.public_thumb.storage.exists(self.photo.public_thumb.name))
        self.assertIn(f"pilgrim-gallery/{self.photo.uuid}/", self.photo.public_large.name)

    def test_unshare_deletes_public_objects_and_clears_flags(self):
        sharing.share_photo(self.photo, credit="anonymous")
        large_path, thumb_path = self.photo.public_large.name, self.photo.public_thumb.name
        storage = self.photo.public_large.storage

        response = self.client.post(reverse("pilgrims:photo_unshare", args=[self.photo.uuid]))
        self.assertTrue(response.json()["success"])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.is_public_on_site)
        self.assertIsNone(self.photo.public_shared_at)
        self.assertEqual(self.photo.public_credit, "")
        self.assertFalse(storage.exists(large_path))
        self.assertFalse(storage.exists(thumb_path))

    def test_public_copy_exists_exactly_as_long_as_the_share_does(self):
        # Both directions, explicitly: share -> exists; unshare -> gone.
        storage = self.photo.public_large.storage
        self.assertFalse(bool(self.photo.public_large))

        sharing.share_photo(self.photo, credit="display_name")
        self.photo.refresh_from_db()
        self.assertTrue(storage.exists(self.photo.public_large.name))

        path_before = self.photo.public_large.name
        sharing.unshare_photo(self.photo)
        self.photo.refresh_from_db()
        self.assertFalse(storage.exists(path_before))
        self.assertFalse(bool(self.photo.public_large))

    def test_public_copy_has_no_exif(self):
        # Upload a photo with real GPS+orientation EXIF, share it, and
        # confirm the PUBLIC copy carries none at all (not just no GPS).
        from PIL import Image
        from .factories import GPS_IFD_TAG, ORIENTATION_TAG

        photo = _make_photo(self.owner, self.site, with_gps=True, orientation=6)
        sharing.share_photo(photo, credit="display_name")
        photo.refresh_from_db()

        with photo.public_large.open("rb") as f:
            image = Image.open(f)
            image.load()
            exif = image.getexif()
        self.assertNotIn(GPS_IFD_TAG, exif)
        self.assertNotIn(ORIENTATION_TAG, exif)
        self.assertEqual(len(dict(exif)), 0, "public copy should carry no EXIF tags at all")

    def test_unverified_account_cannot_share(self):
        unverified = User.objects.create_user("unverified_sharer", "unverified@example.com", "pw")
        photo = _make_photo(unverified, self.site)
        client = Client()
        client.force_login(unverified)
        response = client.post(reverse("pilgrims:photo_share", args=[photo.uuid]), {"credit": "display_name"})
        data = response.json()
        self.assertFalse(data["success"])
        photo.refresh_from_db()
        self.assertFalse(photo.is_public_on_site)

    def test_suspended_owner_cannot_share(self):
        self.owner.pilgrim.can_share_publicly = False
        self.owner.pilgrim.save(update_fields=["can_share_publicly"])
        response = self.client.post(
            reverse("pilgrims:photo_share", args=[self.photo.uuid]), {"credit": "display_name"}
        )
        self.assertFalse(response.json()["success"])

    def test_stranger_cannot_share_someone_elses_photo(self):
        stranger = User.objects.create_user("share_stranger", "share_stranger@example.com", "pw")
        verify_email(stranger)
        client = Client()
        client.force_login(stranger)
        response = client.post(
            reverse("pilgrims:photo_share", args=[self.photo.uuid]), {"credit": "display_name"}
        )
        self.assertFalse(response.json()["success"])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.is_public_on_site)

    def test_share_rate_limit(self):
        from ..views import PUBLIC_SHARES_PER_DAY

        photos = [_make_photo(self.owner, self.site, width=50 + i, height=50 + i) for i in range(PUBLIC_SHARES_PER_DAY)]
        for photo in photos:
            sharing.share_photo(photo, credit="display_name")

        one_more = _make_photo(self.owner, self.site, width=999, height=999)
        response = self.client.post(
            reverse("pilgrims:photo_share", args=[one_more.uuid]), {"credit": "display_name"}
        )
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")


class GalleryQueryPermissionTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("gallery_owner", "gallery_owner@example.com", "pw")
        verify_email(self.owner)
        self.site = _make_site()

    def test_can_share_photo_permission(self):
        photo = _make_photo(self.owner, self.site)
        self.assertTrue(can_share_photo(self.owner, photo))
        stranger = User.objects.create_user("gallery_stranger", "gallery_stranger@example.com", "pw")
        self.assertFalse(can_share_photo(stranger, photo))
