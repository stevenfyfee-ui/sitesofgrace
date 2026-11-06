"""The switch: three modes, typo means off, and the 404 / noindex / sitemap / search gating."""
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings

from future_saints.switch import future_saints_enabled, future_saints_mode, future_saints_public

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase


class Req:
    def __init__(self, user):
        self.user = user


class ModeTests(SimpleTestCase):
    def test_modes(self):
        User = get_user_model()
        staff = User(username="s", is_staff=True)
        visitor = User(username="v")
        with override_settings(SOG_FUTURE_SAINTS="off"):
            self.assertFalse(future_saints_enabled(Req(staff)))
            self.assertFalse(future_saints_public())
        with override_settings(SOG_FUTURE_SAINTS="staff"):
            self.assertTrue(future_saints_enabled(Req(staff)))
            self.assertFalse(future_saints_enabled(Req(visitor)))
            self.assertFalse(future_saints_public())
        with override_settings(SOG_FUTURE_SAINTS="on"):
            self.assertTrue(future_saints_enabled(Req(visitor)))
            self.assertTrue(future_saints_public())
        with override_settings(SOG_FUTURE_SAINTS="yes please"):
            self.assertEqual(future_saints_mode(), "off", "an unknown value must read as off")
            self.assertFalse(future_saints_enabled(Req(staff)))

    def test_default_is_off(self):
        from django.conf import settings
        self.assertEqual(settings.SOG_FUTURE_SAINTS, "off")

    def test_template_tag_matches_helper(self):
        template = Template("{% load future_saints_tags %}{% future_saints_enabled as fs %}{{ fs }}")
        request = RequestFactory().get("/")
        request.user = get_user_model()(username="s", is_staff=True)
        with override_settings(SOG_FUTURE_SAINTS="staff"):
            self.assertEqual(template.render(Context({"request": request})), "True")
        with override_settings(SOG_FUTURE_SAINTS="off"):
            self.assertEqual(template.render(Context({"request": request})), "False")


class GateTests(FutureSaintsTestCase):
    URLS = ("/future-saints/", "/future-saints/saints/", "/future-saints/holy-land/")

    def test_off_is_404_for_everyone(self):
        with FS_OFF:
            for url in self.URLS:
                for user in (None, self.visitor, self.staff):
                    self.assertEqual(self.get(url, user).status_code, 404, (url, user))

    def test_staff_mode_is_staff_only(self):
        with FS_STAFF:
            for url in self.URLS:
                self.assertEqual(self.get(url).status_code, 404, url)
                self.assertEqual(self.get(url, self.visitor).status_code, 404, url)
                self.assertEqual(self.get(url, self.staff).status_code, 200, url)

    def test_on_is_public(self):
        with FS_ON:
            for url in self.URLS:
                self.assertEqual(self.get(url).status_code, 200, url)

    def test_unpublished_pages_still_404(self):
        self.saints.unpublish()
        with FS_ON:
            self.assertEqual(self.get("/future-saints/saints/", self.staff).status_code, 404)

    def test_noindex_until_on(self):
        with FS_STAFF:
            response = self.get("/future-saints/", self.staff)
            self.assertContains(response, '<meta name="robots" content="noindex,nofollow">')
            self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
            self.assertIn("private", response["Cache-Control"])
        with FS_ON:
            response = self.get("/future-saints/")
            self.assertNotContains(response, 'name="robots"')
            self.assertFalse(response.has_header("X-Robots-Tag"))

    def test_sitemap_until_on(self):
        for mode in (FS_OFF, FS_STAFF):
            with mode:
                self.assertNotContains(self.get("/sitemap.xml"), "/future-saints/")
                self.assertNotContains(self.get("/sitemap.xml", self.staff), "/future-saints/")
        with FS_ON:
            body = self.get("/sitemap.xml").content.decode()
            self.assertIn("/future-saints/", body)
            self.assertIn("/future-saints/saints/", body)

    def test_never_in_site_search(self):
        # The only /future-saints/ links on a search page may be the adult
        # header's own menu item (main + mobile), never a result.
        for mode in (FS_OFF, FS_STAFF, FS_ON):
            with mode:
                for user in (None, self.staff):
                    menu_links = self.get("/", user).content.decode().count("/future-saints/")
                    for q in ("Future Saints", "Saints", "Holy Land"):
                        html = self.get("/search/", user, q=q).content.decode()
                        self.assertEqual(html.count("/future-saints/"), menu_links, (q, user))
