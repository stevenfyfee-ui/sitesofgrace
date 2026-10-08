"""
The pilgrim profile page's Visited / Want-to-Go tile images and the
shared-photos grid — specifically the viewer-dependent photo rule in
permissions.profile_photos_for: the owner may see any of their own photos
there, everyone else only publicly shared, un-hidden, credited ones.

"Not on the page" is asserted on the photo's uuid, which is in the path of
every derivative of it, private and public — so no URL of any size of that
photo can be in the markup.
"""
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from wagtail.images import get_image_model

from .. import sharing
from ..models import Follow, PilgrimProfile, SiteVisit
from .factories import make_jpeg_bytes
from .test_sharing import _make_photo, _make_site, _PublicAndPrivateStorageTestCase


def _make_site_with_image(slug, title):
    site = _make_site(slug=slug, title=title)
    image = get_image_model().objects.create(
        title=f"{title} image", file=ContentFile(make_jpeg_bytes(width=900, height=500), name=f"{slug}-featimg.jpg"),
    )
    site.featured_image = image
    site.save_revision().publish()
    site.refresh_from_db()
    return site


class _ProfilePageTestCase(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("prof_owner", "prof_owner@example.com", "pw")
        self.profile = self.owner.pilgrim
        self.follower = User.objects.create_user("prof_follower", "prof_follower@example.com", "pw")
        Follow.objects.create(follower=self.follower, following=self.owner, status=Follow.STATUS_ACCEPTED)
        self.stranger = User.objects.create_user("prof_stranger", "prof_stranger@example.com", "pw")
        self.url = reverse("pilgrims:profile_detail", args=[self.profile.handle])

    def _make_public(self):
        self.profile.is_private = False
        self.profile.save(update_fields=["is_private"])

    def _get(self, user=None, url=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        response = client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class SiteTileImageTests(_ProfilePageTestCase):
    def setUp(self):
        super().setUp()
        self.site = _make_site_with_image("tile-shrine", "Tile Shrine")
        SiteVisit.objects.create(owner=self.owner, site=self.site, status=SiteVisit.STATUS_VISITED)
        self.private_photo = _make_photo(self.owner, self.site)
        # Rendition filenames start with the original's stem; "-featimg" keeps
        # this from matching the site's own URL.
        self.site_image_marker = f"{self.site.slug}-featimg"

    def test_owner_sees_their_private_photo_as_the_tile(self):
        content = self._get(self.owner)
        self.assertIn(self.private_photo.thumb.url, content)
        self.assertNotIn(self.site_image_marker, content)

    def test_follower_sees_the_site_image_not_the_private_photo(self):
        content = self._get(self.follower)
        self.assertNotIn(str(self.private_photo.uuid), content)
        self.assertIn(self.site_image_marker, content)

    def test_anonymous_visitor_sees_the_site_image_not_the_private_photo(self):
        self._make_public()
        content = self._get()
        self.assertNotIn(str(self.private_photo.uuid), content)
        self.assertIn(self.site_image_marker, content)

    def test_logged_in_stranger_on_public_profile_sees_the_site_image(self):
        self._make_public()
        content = self._get(self.stranger)
        self.assertNotIn(str(self.private_photo.uuid), content)
        self.assertIn(self.site_image_marker, content)

    def test_follower_sees_a_shared_photo_via_its_public_derivative(self):
        sharing.share_photo(self.private_photo, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)
        content = self._get(self.follower)
        self.assertIn(self.private_photo.public_thumb.url, content)
        # Never the presigned private URL, even for a photo that's public.
        self.assertNotIn(self.private_photo.thumb.url, content)

    def test_shared_then_hidden_by_staff_stops_appearing_immediately(self):
        sharing.share_photo(self.private_photo, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)
        self.assertIn(str(self.private_photo.uuid), self._get(self.follower))

        sharing.hide_photo(self.private_photo, reason="test")
        content = self._get(self.follower)
        self.assertNotIn(str(self.private_photo.uuid), content)
        self.assertIn(self.site_image_marker, content)

    def test_anonymously_credited_share_is_not_attributed_on_the_profile(self):
        sharing.share_photo(self.private_photo, credit=PilgrimProfile.CREDIT_ANONYMOUS)
        content = self._get(self.follower)
        self.assertNotIn(str(self.private_photo.uuid), content)
        self.assertIn(self.site_image_marker, content)

    def test_owner_tile_srcset_offers_both_signed_derivatives(self):
        content = self._get(self.owner)
        photo = self.private_photo
        self.assertIn(
            f'srcset="{photo.thumb.url} 400w, {photo.large.url} {photo.large_width}w"', content
        )
        # Phones: only the thumb, via the <img> fallback outside the media-gated <source>.
        self.assertIn('<source media="(min-width: 641px)"', content)
        self.assertIn(f'<img src="{photo.thumb.url}" alt="" loading="lazy">', content)

    def test_shared_tile_srcset_uses_public_derivatives_only(self):
        sharing.share_photo(self.private_photo, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)
        photo = self.private_photo
        content = self._get(self.follower)
        self.assertIn(
            f'srcset="{photo.public_thumb.url} 400w, {photo.public_large.url} {photo.large_width}w"',
            content,
        )
        self.assertNotIn(photo.large.url, content)
        self.assertNotIn(photo.thumb.url, content)

    def test_large_width_matches_the_stored_derivative(self):
        from PIL import Image

        for size in ((2400, 1800), (1800, 2400), (900, 600)):
            with self.subTest(size=size):
                photo = _make_photo(self.owner, self.site, width=size[0], height=size[1])
                with photo.large.open("rb") as f:
                    self.assertEqual(Image.open(f).size[0], photo.large_width)

    def test_branded_fallback_when_no_photo_and_no_site_image(self):
        bare = _make_site(slug="bare-shrine", title="Bare Shrine")
        SiteVisit.objects.create(owner=self.owner, site=bare, status=SiteVisit.STATUS_WANT_TO_GO)
        content = self._get(self.follower)
        self.assertIn("pilgrim-site-tile-img--fallback", content)
        self.assertIn('<span class="pilgrim-site-tile-fallback-title">Bare Shrine</span>', content)

    def test_every_tile_links_to_the_public_site_page(self):
        content = self._get(self.follower)
        self.assertIn(f'class="pilgrim-site-tile" href="{self.site.url}"', content)


class SharedPhotosGridTests(_ProfilePageTestCase):
    def setUp(self):
        super().setUp()
        self.site = _make_site(slug="shared-grid-shrine", title="Shared Grid Shrine")

    def test_owner_sees_empty_state_with_library_link(self):
        content = self._get(self.owner)
        self.assertIn('id="shared-photos"', content)
        self.assertIn(reverse("pilgrims:photo_library"), content)

    def test_other_viewers_see_no_section_when_nothing_shared(self):
        self._make_public()
        _make_photo(self.owner, self.site)  # private only
        for user in (self.follower, self.stranger, None):
            content = self._get(user)
            self.assertNotIn('id="shared-photos"', content)
            self.assertNotIn("Shared Photos", content)

    def test_only_shared_unhidden_photos_appear_linked_to_the_gallery(self):
        shared = _make_photo(self.owner, self.site)
        sharing.share_photo(shared, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)
        private = _make_photo(self.owner, self.site, color=(10, 200, 10))
        hidden = _make_photo(self.owner, self.site, color=(10, 10, 200))
        sharing.share_photo(hidden, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)
        sharing.hide_photo(hidden, reason="test")

        content = self._get(self.follower)
        self.assertIn("Shared Photos <span class=\"passport-count\">(1)</span>", content)
        self.assertIn(shared.public_thumb.url, content)
        self.assertIn(f'href="{self.site.url}gallery/"', content)
        self.assertNotIn(str(private.uuid), content)
        self.assertNotIn(str(hidden.uuid), content)

    def test_anonymous_credit_shown_to_owner_only(self):
        anon = _make_photo(self.owner, self.site)
        sharing.share_photo(anon, credit=PilgrimProfile.CREDIT_ANONYMOUS)
        self.assertIn(anon.public_thumb.url, self._get(self.owner))
        self.assertNotIn(str(anon.uuid), self._get(self.follower))

    def test_paginates(self):
        from ..views import PROFILE_SHARED_PHOTOS_PAGE_SIZE

        for i in range(PROFILE_SHARED_PHOTOS_PAGE_SIZE + 1):
            sharing.share_photo(_make_photo(self.owner, self.site, color=(i, i, i)), credit="display_name")
        content = self._get(self.follower)
        self.assertEqual(content.count('class="pilgrim-shared-tile"'), PROFILE_SHARED_PHOTOS_PAGE_SIZE)
        self.assertIn("?shared=2#shared-photos", content)
        page_two = self._get(self.follower, url=self.url + "?shared=2")
        self.assertEqual(page_two.count('class="pilgrim-shared-tile"'), 1)


class StubProfileTests(_ProfilePageTestCase):
    def test_private_profile_stub_shows_no_sites_or_photos(self):
        site = _make_site_with_image("stub-shrine", "Stub Shrine")
        SiteVisit.objects.create(owner=self.owner, site=site, status=SiteVisit.STATUS_VISITED)
        photo = _make_photo(self.owner, site)
        sharing.share_photo(photo, credit=PilgrimProfile.CREDIT_DISPLAY_NAME)

        for user in (self.stranger, None):
            content = self._get(user)
            self.assertIn("pilgrim-private-notice", content)
            self.assertNotIn("Stub Shrine", content)
            self.assertNotIn(str(photo.uuid), content)
            self.assertNotIn("pilgrim-site-grid", content)
            self.assertNotIn("Shared Photos", content)


class ProfileQueryCountTests(_ProfilePageTestCase):
    def _add_sites(self, start, count):
        for i in range(start, start + count):
            site = _make_site_with_image(f"qc-shrine-{i}", f"QC Shrine {i}")
            status = SiteVisit.STATUS_VISITED if i % 2 else SiteVisit.STATUS_WANT_TO_GO
            SiteVisit.objects.create(owner=self.owner, site=site, status=status)
            # Every other site gets a photo (shared on some), so all three tile
            # sources are exercised.
            if i % 2:
                photo = _make_photo(self.owner, site, color=(i, 0, 0))
                if i % 4 == 1:
                    sharing.share_photo(photo, credit="display_name")

    def _steady_state_queries(self, user):
        client = Client()
        if user is not None:
            client.force_login(user)
        client.get(self.url)  # first render generates any missing renditions
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_number_of_sites(self):
        for user in (self.owner, self.follower):
            with self.subTest(viewer=user.username):
                SiteVisit.objects.filter(owner=self.owner).delete()
                self._add_sites(0 if user is self.owner else 100, 2)
                small = self._steady_state_queries(user)
                self._add_sites(10 if user is self.owner else 110, 8)

                client = Client()
                client.force_login(user)
                client.get(self.url)
                with self.assertNumQueries(small):
                    client.get(self.url)
