"""The Future Saints banner on the adult homepage (home/includes/_future_saints_banner.html):
only there, only while Future Saints is live for the request; editable texts with defaults;
feature links only to live pages; no shopping or affiliate words; the button's contrast."""
import datetime
import re
from pathlib import Path

from django.conf import settings

from future_saints.models import GrownUpsNotePage, WorldMapPage
from home.models import HomePage

from .base import FS_OFF, FS_ON, FutureSaintsTestCase

HOME_CSS = Path(settings.BASE_DIR) / "sitesofgrace" / "static" / "css" / "home.css"
SHOPPING = ("buy", "shop", "store", "price", "sale", "deal", "amazon", "amzn", "affiliate", "sponsored", "order")


def banner(html):
    return html.split('<section class="fs-promo"', 1)[1].split("</section>", 1)[0]


def luminance(hex_color):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


class BannerTests(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        self.homepage = HomePage.objects.get()

    def test_only_on_the_homepage_and_only_when_live(self):
        with FS_ON:
            self.assertEqual(self.html("/").count('class="fs-promo"'), 1)
            self.assertNotIn("fs-promo", self.html("/search/", q="lourdes"), "homepage only")
            self.assertNotIn("fs-promo", self.html("/future-saints/"), "not on Future Saints pages")
        with FS_OFF:
            self.assertNotIn("fs-promo", self.html("/"))
        self.home.unpublish()
        with FS_ON:
            self.assertNotIn("fs-promo", self.html("/"), "hidden while the Future Saints home isn't live")

    def test_placed_right_after_the_section_above(self):
        with FS_ON:
            html = self.html("/")
        start = html.index('<section class="fs-promo"')
        self.assertLess(html.index('class="hero'), start)
        self.assertTrue(html[:start].rstrip().endswith("</section>"), "directly after the section above it")
        if 'class="feature-cards"' in html:
            self.assertLess(html.index('class="feature-cards"'), start)

    def test_default_texts_button_and_placeholder(self):
        with FS_ON:
            b = banner(self.html("/"))
        for text in ("Future Saints", "Catholic Faith &amp; Holy Places for Kids", "Saint Stories for Kids",
                     "Holy Places Around the World", "Fun Faith Activities", "For Parents, Teachers &amp; Homeschool",
                     "A fun, faith-filled place for Catholic kids (Grades 2–5)!",
                     "Discover amazing saints, holy places, and true stories of faith, with maps, quizzes, "
                     "printables, and resources for parents, teachers, and homeschool families."):
            self.assertIn(text, b)
        button = b.split('<a class="fs-promo-btn" href="/future-saints/">', 1)[1].split("</a>", 1)[0]
        self.assertIn("<span>Visit Future Saints →</span>", button)
        self.assertLess(button.index("<svg"), button.index("Visit Future Saints"), "the people icon comes first")
        self.assertIn('class="fs-promo-frame" aria-hidden="true"', b, "placeholder art without a picture")
        self.assertNotIn("credit", b.lower())

    def test_edited_texts_show_and_blank_falls_back(self):
        self.homepage.fs_banner_heading = "Edited heading (sample)"
        self.homepage.fs_banner_button_label = ""
        self.homepage.save_revision().publish()
        with FS_ON:
            b = banner(self.html("/"))
        self.assertIn("Edited heading (sample)", b)
        self.assertIn("<span>Visit Future Saints →</span></a>", b, "a blank label shows its default")

    def test_feature_links_only_to_live_pages(self):
        with FS_ON:
            b = banner(self.html("/"))
        self.assertIn('href="/future-saints/saints/"', b)
        for path in ("/future-saints/map/", "/future-saints/california-missions/projects/", "/future-saints/for-grown-ups/"):
            self.assertNotIn(f'href="{path}"', b, "not live here: label only")
        self.assertIn('<span class="fs-promo-feature">', b)
        self.publish(WorldMapPage.objects.get())
        note = GrownUpsNotePage.objects.get()
        note.effective_date = datetime.date(2026, 12, 1)
        note.save_revision().publish()
        with FS_ON:
            b = banner(self.html("/"))
        self.assertIn('href="/future-saints/map/"', b)
        self.assertIn('href="/future-saints/for-grown-ups/"', b)

    def test_no_shopping_or_affiliate_words(self):
        with FS_ON:
            text = re.sub(r"<[^>]+>", " ", banner(self.html("/"))).lower()
        for word in SHOPPING:
            self.assertIsNone(re.search(rf"\b{word}\b", text), word)

    def test_button_contrast_at_least_4_5(self):
        css = HOME_CSS.read_text(encoding="utf-8")
        purple = re.search(r"\.fs-promo \{[^}]*--fs-purple:\s*(#[0-9A-Fa-f]{6})", css).group(1)
        rule = re.search(r"\.fs-promo-btn \{([^}]*)\}", css).group(1)
        self.assertIn("background: var(--fs-purple)", rule)
        self.assertIn("color: #fff", rule)
        self.assertIn("min-height: 46px", rule, "44px+ tap target")
        ratio = 1.05 / (luminance(purple) + 0.05)
        self.assertGreaterEqual(ratio, 4.5, f"{purple} vs white: {ratio:.2f}")
        self.assertRegex(css, r"\.fs-promo-btn:focus-visible[^{]*\{\s*outline: 3px solid")
