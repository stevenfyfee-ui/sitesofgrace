"""Child-safe boundary: no cookies, no third-party hosts, no commerce, sign-in,
newsletter or donation anything in Future Saints HTML."""
import re

from .base import FS_ON, FS_STAFF, FutureSaintsTestCase

BANNED = (
    "tp-em.com", "fonts.googleapis", "fonts.gstatic", "esri", "amazon.", "amzn", "affiliate",
    "booking", "/plan/", "newsletter", "sign in", "sign up", "signin", "signup", "donate",
    "csrfmiddlewaretoken", "/accounts/", "/pilgrims/", "/store/",
)
PAGES = (
    "/future-saints/", "/future-saints/saints/", "/future-saints/marian-apparitions/",
    "/future-saints/eucharistic-miracles/", "/future-saints/holy-land/", "/future-saints/california-missions/",
)


class BoundaryTests(FutureSaintsTestCase):
    def rendered(self):
        with FS_STAFF:
            for url in PAGES:
                yield url, "staff", self.html(url, self.staff)
        with FS_ON:
            for url in PAGES:
                yield url, "anonymous", self.html(url)
                yield url, "anonymous ?level", self.html(url, level="explorer")

    def test_no_banned_strings(self):
        for url, who, html in self.rendered():
            lower = html.lower()
            for word in BANNED:
                self.assertNotIn(word, lower, f"{word!r} on {url} ({who})")

    def test_no_third_party_hosts(self):
        for url, who, html in self.rendered():
            hosts = set(re.findall(r'(?:src|href|action)="(?:https?:)?//([^/"]+)', html))
            hosts -= {"www.w3.org"}
            self.assertEqual(hosts, set(), f"{url} ({who})")
            self.assertNotIn("<iframe", html)

    def test_no_post_forms(self):
        for url, who, html in self.rendered():
            for form in re.findall(r"<form[^>]*>", html):
                self.assertIn('method="get"', form, f"{url} ({who})")

    def test_anonymous_visit_sets_no_cookies(self):
        with FS_ON:
            for url in ("/future-saints/", "/future-saints/saints/"):
                for params in ({}, {"level": "researcher"}):
                    self.client.cookies.clear()
                    response = self.get(url, **params)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(dict(response.cookies), {}, f"{url} {params}")
                    self.assertFalse(response.has_header("Set-Cookie"))

    def test_never_renders_canonical_travel_fields_or_adult_chrome(self):
        with FS_ON:
            html = self.html("/future-saints/")
        for marker in ('class="site-header"', "site-footer", "search-bar", "account-menu", 'class="brand-logo"'):
            self.assertNotIn(marker, html)
