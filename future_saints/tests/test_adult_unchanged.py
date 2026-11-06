"""With the switch off the adult site is byte-for-byte what it was: the menu
item adds nothing (not even whitespace) and costs no query."""
import re

from django.template import Context, Template
from django.test import RequestFactory

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

        # Same switch-independent render when the tag yields "" for another
        # reason (no live home page): the markup around the tag is identical,
        # so the tag itself contributes zero bytes.
        self.home.unpublish()
        with FS_ON:
            self.assertEqual(normalized(self.get("/")), off_anon)
            self.assertEqual(normalized(self.get("/", self.staff)), off_staff)

    def test_staff_mode_shows_the_item_to_staff_only(self):
        with FS_STAFF:
            self.assertNotIn("Future Saints", self.get("/").content.decode())
            html = self.get("/", self.staff).content.decode()
        self.assertEqual(html.count('href="/future-saints/">Future Saints</a>'), 2, "main and mobile menus")

    def test_on_shows_the_item(self):
        with FS_ON:
            html = self.get("/").content.decode()
        self.assertEqual(html.count('href="/future-saints/">Future Saints</a>'), 2)

    def test_menu_tag_costs_no_query_when_off(self):
        request = RequestFactory().get("/")
        request.user = self.staff
        template = Template("{% load future_saints_tags %}{% future_saints_menu_url as link %}[{{ link }}]")
        with FS_OFF, self.assertNumQueries(0):
            self.assertEqual(template.render(Context({"request": request})), "[]")
