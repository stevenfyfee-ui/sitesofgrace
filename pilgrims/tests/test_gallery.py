from django.contrib.auth.models import User
from django.test import Client

from .. import sharing
from ..models import PhotoReport
from .test_sharing import _make_photo, _make_site, _PublicAndPrivateStorageTestCase


class GalleryRenderingTests(_PublicAndPrivateStorageTestCase):
    def setUp(self):
        self.owner = User.objects.create_user("gal_owner", "gal_owner@example.com", "pw")
        self.site = _make_site(slug="render-gallery-site", title="Render Gallery Shrine")
        self.photo = _make_photo(self.owner, self.site)
        sharing.share_photo(self.photo, credit="anonymous")
        self.gallery_url = self.site.url + "gallery/"

    def test_gallery_renders_for_anonymous_visitor(self):
        client = Client()
        response = client.get(self.gallery_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pilgrim Photos")
        self.assertContains(response, "A pilgrim")  # anonymous credit

    def test_gallery_has_no_comment_form(self):
        client = Client()
        response = client.get(self.gallery_url)
        content = response.content.decode()
        # No comment surface at all: no textarea/name="body" comment field,
        # no post-a-comment endpoint anywhere in the markup.
        self.assertNotIn('name="body"', content)
        self.assertNotIn("comment_add", content)
        self.assertNotIn("Write a comment", content)

    def test_gallery_has_no_link_to_private_profile_or_follow_button(self):
        client = Client()
        response = client.get(self.gallery_url)
        content = response.content.decode()
        self.assertNotIn("pilgrims:profile_detail", content)
        self.assertNotIn("pilgrims:follow", content)
        self.assertNotIn(">Follow<", content)

    def test_gallery_has_no_noindex_header(self):
        # NoindexMiddleware forces noindex on /pilgrims/ and /accounts/ only
        # — the gallery lives entirely under the site page's own URL, so it
        # must NOT be caught, in dev or anywhere else.
        client = Client()
        response = client.get(self.gallery_url)
        self.assertIsNone(response.get("X-Robots-Tag"))

    def test_hidden_photo_gallery_url_shows_no_photo(self):
        # There's no per-photo public URL distinct from the gallery listing
        # itself — confirm a hidden photo simply doesn't appear.
        PhotoReport.objects.create(
            photo=self.photo, reporter_ip_hash="x", reason=PhotoReport.REASON_SEXUAL
        )
        from .. import moderation
        moderation.apply_auto_hide_policy(self.photo)

        client = Client()
        response = client.get(self.gallery_url)
        self.assertContains(response, "No photos have been shared here yet.")

    def test_unpublishing_site_page_hides_the_gallery(self):
        self.site.live = False
        self.site.save()
        client = Client()
        response = client.get(self.gallery_url)
        self.assertEqual(response.status_code, 404)

    def test_preview_strip_on_site_page_shows_photo_and_link(self):
        client = Client()
        response = client.get(self.site.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pilgrim Photos")
        self.assertContains(response, "See all 1 pilgrim photo")

    def test_preview_strip_absent_when_no_public_photos(self):
        empty_site = _make_site(slug="empty-gallery-site", title="Empty Site")
        client = Client()
        response = client.get(empty_site.url)
        self.assertNotContains(response, "See all")

    def test_pagination_present_with_many_photos(self):
        for i in range(30):
            photo = _make_photo(self.owner, self.site, width=60 + i, height=60 + i)
            sharing.share_photo(photo, credit="display_name")
        client = Client()
        response = client.get(self.gallery_url)
        self.assertContains(response, "Page 1 of 2")
