"""With the switch off the adult site is byte-for-byte what it was: the
homepage's Future Saints banner adds nothing (not even whitespace) and costs no
query. The "for Kids" strip (PR #34) and the menu item are gone everywhere."""
import re

from django.template import Context, Template
from django.test import RequestFactory

from home.models import HomePage

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase

CSRF = re.compile(r'(name="csrfmiddlewaretoken" value=")[^"]+(")')


def normalized(response):
    return CSRF.sub(r"\1-\2", response.content.decode())


class AdultSiteUnchangedTests(FutureSaintsTestCase):
    def test_switch_off_adds_nothing_to_the_adult_homepage(self):
        with FS_OFF:
            off_anon = normalized(self.get("/"))
            off_staff = normalized(self.get("/", self.staff))
        for html in (off_anon, off_staff):
            self.assertNotIn("future-saints", html)
            self.assertNotIn("Future Saints", html)

        # Same switch-independent render when the tag yields nothing for another
        # reason (no live home page): the markup around the tag is identical,
        # so the tag itself contributes zero bytes.
        self.home.unpublish()
        with FS_ON:
            self.assertEqual(normalized(self.get("/")), off_anon)
            self.assertEqual(normalized(self.get("/", self.staff)), off_staff)

    def test_no_strip_and_no_menu_item_anywhere(self):
        with FS_ON:
            pages = [self.html("/"), self.html("/search/", q="lourdes"), self.get("/no-such-page/").content.decode()]
        for html in pages:
            self.assertNotIn("fs-kids-strip", html)
            self.assertNotIn("fs-kids-pill", html)
            self.assertNotIn(">Future Saints</a>", html, "no Future Saints item in the main or mobile menu")

    def test_banner_tag_costs_no_query_when_off(self):
        request = RequestFactory().get("/")
        request.user = self.staff
        template = Template("{% load future_saints_tags %}{% future_saints_banner page as b %}[{{ b }}]")
        with FS_OFF, self.assertNumQueries(0):
            self.assertEqual(template.render(Context({"request": request, "page": HomePage()})), "[None]")

    def test_staff_mode_shows_the_banner_to_staff_only(self):
        with FS_STAFF:
            self.assertNotIn("Future Saints", self.get("/").content.decode())
            self.assertEqual(self.html("/", self.staff).count('class="fs-promo"'), 1)
