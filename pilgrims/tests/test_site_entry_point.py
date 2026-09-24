"""Adding a photo straight from a sacred site's page: the ?site= preselect
on the upload form, and the "also share publicly" checkbox that runs
through the exact same sharing.py path pilgrims:photo_share uses.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from ..models import PilgrimPhoto, SiteVisit
from .factories import make_uploaded_jpeg, verify_email
from .test_photos import _make_site
from .test_sharing import _PublicAndPrivateStorageTestCase, _make_photo


class UploadPreselectTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("preselect_user", "preselect_user@example.com", "pw")
        self.site = _make_site(slug="preselect-shrine", title="Preselect Shrine")
        self.client = Client()
        self.client.force_login(self.user)

    def test_valid_slug_preselects_the_site(self):
        response = self.client.get(reverse("pilgrims:photo_upload"), {"site": self.site.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["preselected_site"].pk, self.site.pk)
        html = response.content.decode()
        self.assertIn(f'value="{self.site.pk}"', html)
        self.assertIn("Preselect Shrine", html)
        # Arriving from a site page is what flips the share checkbox's
        # default -- confirm the checked attribute is actually there.
        self.assertIn('id="sharePublicly" checked', html.replace("  ", " "))

    def test_unknown_slug_falls_back_to_the_empty_page(self):
        response = self.client.get(reverse("pilgrims:photo_upload"), {"site": "no-such-slug"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["preselected_site"])
        self.assertIn("none yet", response.content.decode())

    def test_non_live_site_falls_back_to_the_empty_page(self):
        draft = _make_site(slug="draft-preselect", title="Draft Shrine", live=False)
        response = self.client.get(reverse("pilgrims:photo_upload"), {"site": draft.slug})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["preselected_site"])

    def test_malformed_value_does_not_500(self):
        response = self.client.get(reverse("pilgrims:photo_upload"), {"site": "../../etc/passwd"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["preselected_site"])

    def test_already_visited_site_unchecks_mark_visited_on_preselect(self):
        SiteVisit.objects.create(owner=self.user, site=self.site, status=SiteVisit.STATUS_VISITED)
        response = self.client.get(reverse("pilgrims:photo_upload"), {"site": self.site.slug})
        html = response.content.decode()
        self.assertNotIn('id="markVisited" checked', html.replace("  ", " "))

    def test_no_param_defaults_share_checkbox_off(self):
        response = self.client.get(reverse("pilgrims:photo_upload"))
        html = response.content.decode()
        self.assertNotIn('id="sharePublicly" checked', html.replace("  ", " "))


class SiteEntryPointSignedOutTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.site = _make_site(slug="signedout-shrine", title="Signed Out Shrine")
        self.client = Client()

    def test_signed_out_visitor_sees_sign_in_variant_on_the_site_page(self):
        response = self.client.get(self.site.url)
        html = response.content.decode()
        self.assertIn("Sign in to add your photos", html)
        self.assertNotIn("Add your photos<", html)

    def test_signed_out_visitor_cannot_post_an_upload(self):
        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(),
        })
        # @login_required redirects to the login page rather than accepting the POST.
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        self.assertEqual(PilgrimPhoto.objects.count(), 0)


class ShareOnUploadTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("share_upload_user", "share_upload_user@example.com", "pw")
        verify_email(self.user)
        self.site = _make_site(slug="share-upload-shrine", title="Share Upload Shrine")
        self.client = Client()
        self.client.force_login(self.user)

    def test_checked_box_shares_the_photo_publicly(self):
        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(),
            "share_publicly": "on",
        })
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["shared"])
        self.assertIsNone(data["share_error"])

        photo = PilgrimPhoto.objects.get(owner=self.user)
        self.assertTrue(photo.is_public_on_site)
        self.assertIn(photo, list(self.site.public_photos_queryset()))

    def test_unchecked_box_keeps_the_photo_private(self):
        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(),
            "share_publicly": "off",
        })
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["shared"])

        photo = PilgrimPhoto.objects.get(owner=self.user)
        self.assertFalse(photo.is_public_on_site)
        self.assertNotIn(photo, list(self.site.public_photos_queryset()))

    def test_share_permission_is_enforced_not_bypassed(self):
        # Same rule photo_share uses: a staff-suspended pilgrim can still
        # upload privately, but the "also share" shortcut can't get around
        # the suspension.
        self.user.pilgrim.can_share_publicly = False
        self.user.pilgrim.save(update_fields=["can_share_publicly"])

        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(),
            "share_publicly": "on",
        })
        data = response.json()
        self.assertTrue(data["success"], "the private upload itself must still succeed")
        self.assertFalse(data["shared"])
        self.assertIsNotNone(data["share_error"])

        photo = PilgrimPhoto.objects.get(owner=self.user)
        self.assertFalse(photo.is_public_on_site)
        self.assertNotIn(photo, list(self.site.public_photos_queryset()))

    def test_share_rate_limit_still_applies_through_the_upload_shortcut(self):
        from ..views import PUBLIC_SHARES_PER_DAY

        existing = [
            _make_photo(self.user, self.site, width=50 + i, height=50 + i)
            for i in range(PUBLIC_SHARES_PER_DAY)
        ]
        for photo in existing:
            from .. import sharing
            sharing.share_photo(photo, credit="display_name")

        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(width=999, height=999),
            "share_publicly": "on",
        })
        data = response.json()
        self.assertTrue(data["success"], "the private upload itself must still succeed")
        self.assertFalse(data["shared"])
        self.assertIn("shared a lot today", data["share_error"])

        photo = PilgrimPhoto.objects.get(owner=self.user, byte_size__gt=0, width=999)
        self.assertFalse(photo.is_public_on_site)

    def test_upload_rate_limit_still_applies_regardless_of_share_checkbox(self):
        from ..views import PHOTO_UPLOADS_PER_HOUR

        for i in range(PHOTO_UPLOADS_PER_HOUR):
            photo = _make_photo(self.user, self.site, width=50 + i, height=50 + i)
            PilgrimPhoto.objects.filter(pk=photo.pk).update(created_at=timezone.now())

        response = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk,
            "photo": make_uploaded_jpeg(width=999, height=999),
            "share_publicly": "on",
        })
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "rate_limited")
