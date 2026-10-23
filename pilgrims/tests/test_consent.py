"""
The public sharing gate (pilgrims/consent.py) on every path that makes a
pilgrim's content public, the private-profile stub, and avatar EXIF.

Share paths covered: the upload page's "also share" box, the photo page's
share form (pilgrims:photo_share), and switching a profile to public.
"""
import io
from io import StringIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from PIL import Image

from ..models import AwardedBadge, Badge, Follow, PilgrimPhoto, PilgrimProfile
from .factories import make_jpeg_bytes, make_uploaded_jpeg, verify_email
from .test_photos import _make_site
from .test_sharing import _make_photo, _PublicAndPrivateStorageTestCase

RIGHTS = {"share_rights": "on"}
ADULT = {"share_adult": "on"}


class _ConsentTestCase(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.user = User.objects.create_user("consent_user", "john.doe@example.com", "pw")
        verify_email(self.user)
        self.site = _make_site(slug="consent-shrine", title="Consent Shrine")
        self.client = Client()
        self.client.force_login(self.user)

    def profile(self):
        return PilgrimProfile.objects.get(user=self.user)


class UploadShareGateTests(_ConsentTestCase):
    def upload(self, **extra):
        data = {"site_id": self.site.pk, "photo": make_uploaded_jpeg(), "share_publicly": "on", **extra}
        return self.client.post(reverse("pilgrims:photo_upload"), data).json()

    def test_refused_without_the_rights_box(self):
        data = self.upload(**ADULT)
        self.assertTrue(data["success"], "the private upload itself still succeeds")
        self.assertFalse(data["shared"])
        self.assertIn("permission to share it", data["share_error"])
        self.assertFalse(PilgrimPhoto.objects.get(owner=self.user).is_public_on_site)

    def test_refused_without_the_adult_confirmation(self):
        data = self.upload(**RIGHTS)
        self.assertFalse(data["shared"])
        self.assertIn("18 or older", data["share_error"])
        self.assertIsNone(self.profile().adult_confirmed_at)

    def test_allowed_with_both_and_records_consent(self):
        data = self.upload(**RIGHTS, **ADULT)
        self.assertTrue(data["shared"])
        photo = PilgrimPhoto.objects.get(owner=self.user)
        self.assertTrue(photo.is_public_on_site)
        self.assertIsNotNone(photo.rights_confirmed_at)
        self.assertIsNotNone(self.profile().adult_confirmed_at)

    def test_adult_box_needed_once_rights_box_every_time(self):
        self.upload(**RIGHTS, **ADULT)
        second = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk, "photo": make_uploaded_jpeg(width=640), "share_publicly": "on", **RIGHTS,
        }).json()
        self.assertTrue(second["shared"])
        third = self.client.post(reverse("pilgrims:photo_upload"), {
            "site_id": self.site.pk, "photo": make_uploaded_jpeg(width=500), "share_publicly": "on",
        }).json()
        self.assertFalse(third["shared"])
        self.assertIn("permission to share it", third["share_error"])

    def test_upload_page_never_pre_ticks_and_hides_adult_box_once_confirmed(self):
        html = self.client.get(reverse("pilgrims:photo_upload"), {"site": self.site.slug}).content.decode()
        self.assertNotIn('id="sharePublicly" checked', html)
        self.assertIn('id="shareRights"', html)
        self.assertIn('id="shareAdult"', html)
        self.assertIn("Public post:", html)
        self.upload(**RIGHTS, **ADULT)
        html = self.client.get(reverse("pilgrims:photo_upload")).content.decode()
        self.assertIn('id="shareRights"', html)
        self.assertNotIn('id="shareAdult"', html)


class PhotoShareGateTests(_ConsentTestCase):
    def setUp(self):
        super().setUp()
        self.photo = _make_photo(self.user, self.site)

    def share(self, photo=None, **extra):
        photo = photo or self.photo
        return self.client.post(
            reverse("pilgrims:photo_share", args=[photo.uuid]), {"credit": "display_name", **extra}
        ).json()

    def test_refused_without_the_rights_box(self):
        data = self.share(**ADULT)
        self.assertFalse(data["success"])
        self.assertIn("permission to share it", data["message"])
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.is_public_on_site)

    def test_refused_without_the_adult_confirmation(self):
        data = self.share(**RIGHTS)
        self.assertFalse(data["success"])
        self.assertIn("18 or older", data["message"])

    def test_allowed_with_both(self):
        self.assertTrue(self.share(**RIGHTS, **ADULT)["success"])
        self.photo.refresh_from_db()
        self.assertTrue(self.photo.is_public_on_site)
        self.assertIsNotNone(self.photo.rights_confirmed_at)

    def test_photo_page_hides_the_adult_box_once_confirmed(self):
        url = reverse("pilgrims:photo_detail", args=[self.photo.uuid])
        html = self.client.get(url).content.decode()
        self.assertIn('name="share_rights"', html)
        self.assertIn('name="share_adult"', html)
        other = _make_photo(self.user, self.site, width=300)
        self.share(other, **RIGHTS, **ADULT)
        html = self.client.get(url).content.decode()
        self.assertIn('name="share_rights"', html)
        self.assertNotIn('name="share_adult"', html)
        self.assertTrue(self.share(**RIGHTS)["success"])


class ProfilePublicGateTests(_ConsentTestCase):
    def post_settings(self, **extra):
        profile = self.profile()
        data = {
            "handle": profile.handle, "display_name": "John Doe", "bio": "", "home_city": "",
            "home_country": "", "dm_policy": profile.dm_policy,
            "public_credit_default": profile.public_credit_default, **extra,
        }
        return self.client.post(reverse("pilgrims:settings"), data)

    def test_going_public_refused_without_adult_confirmation(self):
        response = self.post_settings()  # is_private unticked = public
        self.assertEqual(response.status_code, 200)
        self.assertIn("18 or older to make your profile public", response.content.decode())
        self.assertTrue(self.profile().is_private)

    def test_going_public_allowed_with_it_and_box_disappears(self):
        html = self.client.get(reverse("pilgrims:settings")).content.decode()
        self.assertIn('name="share_adult"', html)
        self.assertIn("Public profile:", html)
        response = self.post_settings(**ADULT)
        self.assertEqual(response.status_code, 302)
        profile = self.profile()
        self.assertFalse(profile.is_private)
        self.assertIsNotNone(profile.adult_confirmed_at)
        html = self.client.get(reverse("pilgrims:settings")).content.decode()
        self.assertNotIn('name="share_adult"', html)

    def test_staying_private_needs_no_confirmation(self):
        response = self.post_settings(is_private="on")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.profile().adult_confirmed_at)


class PrivateProfileStubTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("stub_owner", "stub_owner@example.com", "pw")
        self.profile = self.owner.pilgrim
        self.profile.display_name = "John Doe"
        self.profile.save()
        badge = Badge.objects.create(name="Marian Pilgrim", slug="test-marian-pilgrim")
        AwardedBadge.objects.create(user=self.owner, badge=badge)
        self.approved = User.objects.create_user("stub_approved", "stub_approved@example.com", "pw")
        Follow.objects.create(follower=self.approved, following=self.owner, status=Follow.STATUS_ACCEPTED)
        self.pending = User.objects.create_user("stub_pending", "stub_pending@example.com", "pw")
        Follow.objects.create(follower=self.pending, following=self.owner, status=Follow.STATUS_PENDING)
        self.stranger = User.objects.create_user("stub_stranger", "stub_stranger@example.com", "pw")
        self.url = reverse("pilgrims:profile_detail", args=[self.profile.handle])

    def page(self, user=None):
        client = Client()
        if user:
            client.force_login(user)
        return client.get(self.url).content.decode()

    def assertStub(self, html):
        self.assertIn("John Doe", html)
        self.assertIn(f"@{self.profile.handle}", html)
        self.assertNotIn("Followers", html)
        self.assertNotIn("Marian Pilgrim", html)
        self.assertNotIn(">Badges<", html)

    def assertFull(self, html):
        self.assertIn("Followers", html)
        self.assertIn("Marian Pilgrim", html)

    def test_signed_out(self):
        html = self.page()
        self.assertStub(html)
        self.assertIn("Sign in to follow", html)

    def test_signed_in_non_follower(self):
        self.assertStub(self.page(self.stranger))

    def test_pending_follower(self):
        self.assertStub(self.page(self.pending))

    def test_approved_follower(self):
        self.assertFull(self.page(self.approved))

    def test_owner(self):
        self.assertFull(self.page(self.owner))


class AvatarExifTests(_ConsentTestCase):
    def avatar_has_exif(self, profile):
        with profile.avatar.open("rb") as f:
            image = Image.open(io.BytesIO(f.read()))
            return bool(image.getexif()) or "exif" in image.info

    def test_settings_upload_strips_exif(self):
        profile = self.profile()
        data = {
            "handle": profile.handle, "display_name": "John Doe", "bio": "", "home_city": "",
            "home_country": "", "is_private": "on", "dm_policy": profile.dm_policy,
            "public_credit_default": profile.public_credit_default,
            "avatar": make_uploaded_jpeg(name="me.jpg", with_gps=True, orientation=6),
        }
        response = self.client.post(reverse("pilgrims:settings"), data)
        self.assertEqual(response.status_code, 302)
        profile = self.profile()
        self.assertFalse(self.avatar_has_exif(profile))
        self.assertNotIn("me", profile.avatar.name.rsplit("/", 1)[-1])
        # Orientation 6 (rotate 90) was baked in: 800x600 became 600x800.
        with profile.avatar.open("rb") as f:
            self.assertEqual(Image.open(f).size, (600, 800))

    def test_command_reprocesses_existing_avatars(self):
        profile = self.profile()
        name = profile.avatar.field.generate_filename(profile, "legacy.jpg")
        saved = profile.avatar.storage.save(name, ContentFile(make_jpeg_bytes(with_gps=True)))
        PilgrimProfile.objects.filter(pk=profile.pk).update(avatar=saved)
        self.assertTrue(self.avatar_has_exif(self.profile()))

        out = StringIO()
        call_command("strip_avatar_exif", stdout=out)
        self.assertIn("Cleaned 1 avatar(s)", out.getvalue())
        profile = self.profile()
        self.assertFalse(self.avatar_has_exif(profile))
        self.assertFalse(profile.avatar.storage.exists(saved))

        out = StringIO()
        call_command("strip_avatar_exif", stdout=out)
        self.assertIn("Cleaned 0 avatar(s); 1 already clean", out.getvalue())

