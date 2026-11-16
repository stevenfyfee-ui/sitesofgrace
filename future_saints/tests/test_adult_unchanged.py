"""With the switch off the adult site is byte-for-byte what it was: the
"Future Saints — for Kids" strip adds nothing (not even whitespace) and costs
no query. With it allowed, the strip shows under the adult header (never on
Future Saints pages), and the main and mobile menus have no Future Saints item."""
import re

from django.template import Context, Template
from django.test import RequestFactory

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase

STRIP = '<a class="fs-kids-pill" href="/future-saints/">Future Saints — for Kids <span aria-hidden="true">→</span></a>'
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

        # Same switch-independent render when the tag yields "" for another
        # reason (no live home page): the markup around the tag is identical,
        # so the tag itself contributes zero bytes.
        self.home.unpublish()
        with FS_ON:
            self.assertEqual(normalized(self.get("/")), off_anon)
            self.assertEqual(normalized(self.get("/", self.staff)), off_staff)

    def test_staff_mode_shows_the_strip_to_staff_only(self):
        with FS_STAFF:
            self.assertNotIn("Future Saints", self.get("/").content.decode())
            html = self.get("/", self.staff).content.decode()
        self.assertEqual(html.count(STRIP), 1)

    def test_on_shows_the_strip_under_the_header_and_no_menu_item(self):
        with FS_ON:
            html = self.get("/").content.decode()
        self.assertEqual(html.count(STRIP), 1)
        self.assertIn('<div class="fs-kids-strip">', html.split("</header>", 1)[1].split('<main id="content">', 1)[0],
                      "directly below the header, before the content")
        self.assertNotIn(">Future Saints</a>", html, "no Future Saints item in the main or mobile menu")
        for menu in ('class="primary-nav"', 'id="mobileNav"'):
            self.assertNotIn("/future-saints/", html.split(menu, 1)[1].split("</nav>" if "primary" in menu else "</header>", 1)[0])

    def test_the_strip_is_on_other_adult_pages_but_not_on_future_saints_pages(self):
        with FS_ON:
            self.assertEqual(self.html("/future-saints/").count("fs-kids-strip"), 0, "Future Saints has its own header")
            self.assertEqual(self.get("/search/?q=lourdes").content.decode().count(STRIP), 1)

    def test_menu_tag_costs_no_query_when_off(self):
        request = RequestFactory().get("/")
        request.user = self.staff
        template = Template("{% load future_saints_tags %}{% future_saints_menu_url as link %}[{{ link }}]")
        with FS_OFF, self.assertNumQueries(0):
            self.assertEqual(template.render(Context({"request": request})), "[]")
