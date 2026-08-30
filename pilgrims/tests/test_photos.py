"""
Model/view tests for PilgrimPhoto. These run against a local FileSystemStorage
substituted for "pilgrim_private" (via override_settings) — real Spaces
credentials aren't available in this environment, and swapping storage
backends for tests is standard practice, not a stand-in for the actual
signing behavior (that's covered, without any storage substitution, in
test_storage.py).
"""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from wagtail.models import Page

from catalog.models import SacredSitePage

from ..models import PilgrimPhoto, SiteVisit
from ..permissions import can_view_photo
from .factories import make_uploaded_fake_image, make_uploaded_jpeg


def _make_site(slug="test-shrine", title="Test Shrine", live=True):
    root = Page.objects.get(pk=1)
    site = SacredSitePage(
        title=title, slug=slug, category="Shrine & Basilica", live=live,
    )
    root.add_child(instance=site)
    return site


class _PrivateStorageTestCase(TestCase):
    """Points pilgrim_private at a throwaway local directory for the
    duration of the test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmpdir = tempfile.mkdtemp(prefix="pilgrim_private_test_")
        from django.conf import settings as dj_settings

        storages = dict(dj_settings.STORAGES)
        storages["pilgrim_private"] = {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": cls._tmpdir, "base_url": "/private-test/"},
        }
        cls._override = override_settings(STORAGES=storages)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._tmpdir, ignore_errors=True)
        super().tearDownClass()


class PilgrimPhotoModelTests(_PrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("pat", "pat@example.com", "pw")
        self.site = _make_site()

    def test_create_from_processed_writes_all_four_files(self):
        from .. import imaging

        processed = imaging.process_upload(make_uploaded_jpeg())
        photo = PilgrimPhoto.create_from_processed(
            owner=self.user, site=self.site, processed=processed, caption="Nice",
        )
        self.assertTrue(photo.original.storage.exists(photo.original.name))
        self.assertTrue(photo.large.storage.exists(photo.large.name))
        self.assertTrue(photo.feed.storage.exists(photo.feed.name))
        self.assertTrue(photo.thumb.storage.exists(photo.thumb.name))
        self.assertIn(f"pilgrims/{self.user.pilgrim.uuid}/{photo.uuid}/", photo.original.name)

    def test_delete_removes_all_four_files(self):
        from .. import imaging

        processed = imaging.process_upload(make_uploaded_jpeg())
        photo = PilgrimPhoto.create_from_processed(owner=self.user, site=self.site, processed=processed)
        paths = [photo.original.name, photo.large.name, photo.feed.name, photo.thumb.name]
        storage = photo.original.storage
        photo.delete()
        for path in paths:
            self.assertFalse(storage.exists(path))

    def test_bulk_queryset_delete_also_cleans_up_files(self):
        from .. import imaging

        processed = imaging.process_upload(make_uploaded_jpeg())
        photo = PilgrimPhoto.create_from_processed(owner=self.user, site=self.site, processed=processed)
        storage = photo.original.storage
        path = photo.original.name
        PilgrimPhoto.objects.filter(pk=photo.pk).delete()
        self.assertFalse(storage.exists(path))


class SiteDeletionSafetyTests(_PrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("pat", "pat@example.com", "pw")
        self.site = _make_site()

    def _create_photo(self):
        from .. import imaging

        processed = imaging.process_upload(make_uploaded_jpeg())
        return PilgrimPhoto.create_from_processed(owner=self.user, site=self.site, processed=processed)

    def test_site_with_photos_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        self._create_photo()
        with self.assertRaises(ProtectedError):
            self.site.delete()

    def test_unpublishing_site_does_not_delete_photos(self):
        photo = self._create_photo()
        self.site.live = False
        self.site.save()
        self.assertTrue(PilgrimPhoto.objects.filter(pk=photo.pk).exists())

    def test_before_delete_page_hook_blocks_delete_with_message(self):
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage

        from ..wagtail_hooks import guard_sacred_site_delete

        self._create_photo()
        request = RequestFactory().get("/admin/pages/1/delete/")
        request.session = {}
        request._messages = FallbackStorage(request)

        response = guard_sacred_site_delete(request, self.site)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 302)

    def test_before_delete_page_hook_allows_delete_without_photos(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/pages/1/delete/")
        from ..wagtail_hooks import guard_sacred_site_delete

        response = guard_sacred_site_delete(request, self.site)
        self.assertIsNone(response)


class CanViewPhotoTests(_PrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "pw")
        self.stranger = User.objects.create_user("stranger", "stranger@example.com", "pw")
        self.site = _make_site()
        from .. import imaging

        processed = imaging.process_upload(make_uploaded_jpeg())
        self.photo = PilgrimPhoto.create_from_processed(owner=self.owner, site=self.site, processed=processed)

    def test_owner_can_view(self):
        self.assertTrue(can_view_photo(self.owner, self.photo))

    def test_stranger_cannot_view(self):
        self.assertFalse(can_view_photo(self.stranger, self.photo))


class PhotoUploadViewTests(_PrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("pat", "pat@example.com", "pw")
        self.site = _make_site()
        self.client = Client()
        self.client.force_login(self.user)

    def test_upload_form_renders(self):
        response = self.client.get(reverse("pilgrims:photo_upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload")

    def test_site_search_finds_live_site_and_flags_already_visited(self):
        SiteVisit.objects.create(
            owner=self.user, site=self.site, status=SiteVisit.STATUS_VISITED
        )
        response = self.client.get(reverse("pilgrims:photo_site_search"), {"q": "Test"})
        data = response.json()
        self.assertEqual(len(data["sites"]), 1)
        self.assertEqual(data["sites"][0]["slug"], self.site.slug)
        self.assertTrue(data["sites"][0]["already_visited"])

    def test_site_search_excludes_unpublished_sites(self):
        _make_site(slug="draft-site", title="Draft Shrine", live=False)
        response = self.client.get(reverse("pilgrims:photo_site_search"), {"q": "Draft"})
        self.assertEqual(response.json()["sites"], [])

    def test_upload_success_and_marks_visited(self):
        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(),
            "mark_visited": "on",
        })
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(PilgrimPhoto.objects.filter(owner=self.user).count(), 1)
        self.assertTrue(
            SiteVisit.objects.filter(
                owner=self.user, site=self.site, status=SiteVisit.STATUS_VISITED
            ).exists()
        )

    def test_upload_rejects_bad_file_with_friendly_error(self):
        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_fake_image(),
        })
        self.assertEqual(response.status_code, 200)  # never a 500
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "unsupported")

    def test_duplicate_upload_is_reported_not_stored_twice(self):
        upload = make_uploaded_jpeg()
        from .factories import make_jpeg_bytes
        data_bytes = make_jpeg_bytes()
        from django.core.files.uploadedfile import SimpleUploadedFile

        first = SimpleUploadedFile("a.jpg", data_bytes, content_type="image/jpeg")
        second = SimpleUploadedFile("b.jpg", data_bytes, content_type="image/jpeg")

        r1 = self.client.post(reverse("pilgrims:photo_upload"), {"site_id": self.site.pk, "photo": first})
        self.assertTrue(r1.json()["success"])
        r2 = self.client.post(reverse("pilgrims:photo_upload"), {"site_id": self.site.pk, "photo": second})
        data = r2.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "duplicate")
        self.assertEqual(PilgrimPhoto.objects.filter(owner=self.user).count(), 1)

    def test_rate_limit_returns_friendly_message_not_500(self):
        from datetime import timedelta
        from django.utils import timezone
        from .. import imaging
        from ..views import PHOTO_UPLOADS_PER_HOUR

        processed = imaging.process_upload(make_uploaded_jpeg())
        for i in range(PHOTO_UPLOADS_PER_HOUR):
            photo = PilgrimPhoto.create_from_processed(
                owner=self.user, site=self.site,
                processed=imaging.process_upload(make_uploaded_jpeg(width=50 + i, height=50 + i)),
            )
            PilgrimPhoto.objects.filter(pk=photo.pk).update(created_at=timezone.now())

        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk, "photo": make_uploaded_jpeg(width=999, height=999),
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")


class PhotoLibraryAndAlbumViewTests(_PrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("pat", "pat@example.com", "pw")
        self.other = User.objects.create_user("other", "other@example.com", "pw")
        self.site = _make_site()
        self.client = Client()
        self.client.force_login(self.user)

        from .. import imaging

        self.photo = PilgrimPhoto.create_from_processed(
            owner=self.user, site=self.site, processed=imaging.process_upload(make_uploaded_jpeg())
        )

    def test_library_groups_by_site(self):
        response = self.client.get(reverse("pilgrims:photo_library"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.site.title)

    def test_album_shows_photo(self):
        response = self.client.get(reverse("pilgrims:photo_album", args=[self.site.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.photo.uuid))

    def test_detail_owner_ok_stranger_404(self):
        url = reverse("pilgrims:photo_detail", args=[self.photo.uuid])
        self.assertEqual(self.client.get(url).status_code, 200)

        stranger_client = Client()
        stranger_client.force_login(self.other)
        self.assertEqual(stranger_client.get(url).status_code, 404)

    def test_caption_edit(self):
        response = self.client.post(
            reverse("pilgrims:photo_caption_edit", args=[self.photo.uuid]),
            {"caption": "Updated caption"},
        )
        self.assertTrue(response.json()["success"])
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.caption, "Updated caption")

    def test_bulk_delete(self):
        storage = self.photo.original.storage
        path = self.photo.original.name
        response = self.client.post(reverse("pilgrims:photo_bulk_delete"), {"photo_uuid": [str(self.photo.uuid)]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PilgrimPhoto.objects.filter(pk=self.photo.pk).exists())
        self.assertFalse(storage.exists(path))

    def test_stranger_cannot_delete_others_photo(self):
        stranger_client = Client()
        stranger_client.force_login(self.other)
        response = stranger_client.post(reverse("pilgrims:photo_delete", args=[self.photo.uuid]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PilgrimPhoto.objects.filter(pk=self.photo.pk).exists())


class SacredSiteSlugUniquenessGuardTests(TestCase):
    """The album URL uses the bare slug (confirmed globally unique at the
    time of writing) rather than <pk>-<slug>. This test is the guard the
    phase-2 spec asked for: it fails the moment that stops being true, which
    is exactly when the album URL scheme would need to change."""

    def test_sacred_site_slugs_are_globally_unique(self):
        from django.db.models import Count

        dupes = (
            SacredSitePage.objects.values("slug")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        self.assertEqual(
            list(dupes), [],
            "SacredSitePage slugs are no longer globally unique — the "
            "pilgrims:photo_album URL (which looks up by bare slug) can "
            "now resolve to the wrong site. Switch it to <pk>-<slug>.",
        )
