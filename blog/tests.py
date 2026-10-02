import datetime
import json
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from wagtail.models import Page, PageViewRestriction, Site
from wagtail.test.utils import WagtailPageTestCase

from blog.models import BlogCategory, BlogIndexPage, BlogPostPage, blog_posts
from home.models import AboutPage, HomePage, StorePage


def _words(n):
    return " ".join(["word"] * n)


class BlogFixtureMixin:
    """A HomePage at the site root with a live BlogIndexPage at /blog/."""

    def make_site(self, with_index=True):
        root = Page.get_first_root_node()
        # Wagtail caches site root paths outside the test transaction, so the
        # Site swapped in below would outlive the rollback and 404 every page
        # in whichever test module runs next. Clear it on the way out.
        self.addCleanup(Site.clear_site_root_paths_cache)
        Site.objects.all().delete()
        self.home = HomePage(title="Home", slug="home-test")
        root.add_child(instance=self.home)
        Site.objects.create(hostname="localhost", port=80, root_page=self.home, is_default_site=True)
        self.cats = {c.slug: c for c in BlogCategory.objects.all()}
        if with_index:
            self.index = BlogIndexPage(title="Blog")
            self.home.add_child(instance=self.index)
            self.index.save_revision().publish()

    def make_post(self, title, date, cats=("sites",), live=True, body_words=0, publish=True):
        post = BlogPostPage(
            title=title, date=date, excerpt=f"About {title}.",
            body=json.dumps([{"type": "paragraph", "value": f"<p>{_words(body_words)}</p>"}]) if body_words else "[]",
        )
        post.categories = [self.cats[c] for c in cats]
        self.index.add_child(instance=post)
        if publish:
            post.save_revision().publish()
        if not live:
            post.unpublish()
        return BlogPostPage.objects.get(pk=post.pk)


class BlogStructureTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site(with_index=False)

    def test_index_creatable_only_under_homepage(self):
        self.assertCanCreateAt(HomePage, BlogIndexPage)
        self.assertCanNotCreateAt(StorePage, BlogIndexPage)
        self.assertCanNotCreateAt(BlogIndexPage, BlogIndexPage)

    def test_index_max_count_one(self):
        self.home.add_child(instance=BlogIndexPage(title="Blog"))
        self.assertFalse(BlogIndexPage(title="Blog 2").can_create_at(self.home))

    def test_index_defaults(self):
        index = BlogIndexPage(title="Blog")
        self.assertEqual(index.slug, "blog")
        self.assertEqual(index.eyebrow, "From the Pilgrim's Desk")
        self.assertEqual(index.posts_per_page, 12)

    def test_post_only_under_index(self):
        self.assertCanCreateAt(BlogIndexPage, BlogPostPage)
        self.assertCanNotCreateAt(HomePage, BlogPostPage)
        self.assertCanNotCreateAt(StorePage, BlogPostPage)
        self.assertEqual(BlogPostPage.subpage_types, [])


class CategorySeedTests(TestCase):
    def test_four_categories_seeded_in_order(self):
        self.assertEqual(
            list(BlogCategory.objects.values_list("name", "slug", "sort_order")),
            [("Sites", "sites", 10), ("Travel", "travel", 20), ("Saints", "saints", 30), ("Other", "other", 90)],
        )
        self.assertEqual(
            BlogCategory.objects.get(slug="travel").description,
            "Practical pilgrimage planning: getting there, where to stay, what to know.",
        )


class PostValidationTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)

    def _post(self, categories):
        data = {
            "title": "No category post", "slug": "no-category-post", "date": "2026-09-01",
            "author_name": "Steven Fyffe", "excerpt": "An excerpt.", "body-count": "0",
            "related_pages-TOTAL_FORMS": "0", "related_pages-INITIAL_FORMS": "0",
            "related_pages-MIN_NUM_FORMS": "0", "related_pages-MAX_NUM_FORMS": "3",
            "action-publish": "action-publish",
        }
        if categories:
            data["categories"] = [c.pk for c in categories]
        return self.client.post(f"/admin/pages/add/blog/blogpostpage/{self.index.pk}/", data)

    def test_post_with_no_categories_fails_validation(self):
        response = self._post([])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose at least one category for this post.")
        self.assertFalse(BlogPostPage.objects.exists())

    def test_post_with_a_category_publishes(self):
        response = self._post([self.cats["travel"]])
        self.assertEqual(response.status_code, 302)
        post = BlogPostPage.objects.get()
        self.assertTrue(post.live)
        self.assertEqual([c.slug for c in post.categories.all()], ["travel"])


class IndexListingTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()

    def test_newest_first_with_tie_break_and_no_drafts_or_private(self):
        old = self.make_post("Old", datetime.date(2026, 1, 1))
        tie_first = self.make_post("Tie published first", datetime.date(2026, 5, 1))
        tie_second = self.make_post("Tie published second", datetime.date(2026, 5, 1))
        newest = self.make_post("Newest", datetime.date(2026, 6, 1))
        self.make_post("Draft", datetime.date(2026, 7, 1), live=False)
        private = self.make_post("Private", datetime.date(2026, 8, 1))
        PageViewRestriction.objects.create(page=private, restriction_type="login")

        self.assertEqual(
            [p.title for p in blog_posts()],
            [newest.title, tie_second.title, tie_first.title, old.title],
        )
        response = self.client.get("/blog/")
        self.assertEqual(response.context["featured_post"].pk, newest.pk)
        self.assertEqual([p.pk for p in response.context["posts"]], [tie_second.pk, tie_first.pk, old.pk])
        self.assertNotContains(response, "Draft")
        self.assertNotContains(response, "Private")

    def test_featured_not_duplicated_and_pagination(self):
        self.index.posts_per_page = 2
        self.index.save_revision().publish()
        posts = [self.make_post(f"Post {i}", datetime.date(2026, 1, i + 1)) for i in range(6)]
        newest = posts[-1]

        page1 = self.client.get("/blog/")
        grid1 = [p.pk for p in page1.context["posts"]]
        self.assertEqual(page1.context["featured_post"].pk, newest.pk)
        self.assertNotIn(newest.pk, grid1)
        self.assertEqual(len(grid1), 2)
        self.assertEqual(page1.content.decode().count(f'href="{newest.url}"'), 1)

        page2 = self.client.get("/blog/?page=2")
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(page2.context["page_obj"].number, 2)
        self.assertIsNone(page2.context["featured_post"])
        self.assertTrue(set(p.pk for p in page2.context["posts"]).isdisjoint(grid1))
        self.assertContains(page2, "Page 2 of 3")

        for bad in ("999", "abc"):
            response = self.client.get(f"/blog/?page={bad}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_obj"].number, 1)

    def test_category_pages(self):
        travel = self.make_post("Rail travel", datetime.date(2026, 3, 1), cats=["travel"])
        both = self.make_post("Sites and travel", datetime.date(2026, 2, 1), cats=["sites", "travel"])
        sites = self.make_post("Only sites", datetime.date(2026, 1, 1), cats=["sites"])

        response = self.client.get("/blog/category/travel/")
        self.assertEqual(response.status_code, 200)
        shown = {response.context["featured_post"].pk} | {p.pk for p in response.context["posts"]}
        self.assertEqual(shown, {travel.pk, both.pk})
        self.assertEqual(response.context["active_category"].slug, "travel")
        self.assertContains(response, 'aria-current="page">Travel</a>')

        sites_page = self.client.get("/blog/category/sites/")
        shown = {sites_page.context["featured_post"].pk} | {p.pk for p in sites_page.context["posts"]}
        self.assertEqual(shown, {both.pk, sites.pk})

        self.assertEqual(self.client.get("/blog/category/nope/").status_code, 404)

    def test_empty_states(self):
        response = self.client.get("/blog/")
        self.assertContains(response, "The first stories are on their way")
        self.assertNotContains(response, 'class="blog-grid"')

        self.make_post("Rail travel", datetime.date(2026, 3, 1), cats=["travel"])
        response = self.client.get("/blog/category/other/")
        self.assertContains(response, "No posts in Other yet. Check back soon.")
        self.assertContains(response, 'href="/blog/"')
        self.assertNotContains(response, 'class="blog-grid"')

    def test_chips_hide_empty_categories(self):
        self.make_post("Rail travel", datetime.date(2026, 3, 1), cats=["travel"])
        content = self.client.get("/blog/").content.decode()
        self.assertIn('href="/blog/category/travel/"', content)
        self.assertNotIn('href="/blog/category/saints/"', content)

    def test_feed(self):
        posts = [self.make_post(f"Feed post {i}", datetime.date(2025, 1, 1) + datetime.timedelta(days=i)) for i in range(22)]
        response = self.client.get("/blog/feed/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/rss+xml"))
        content = response.content.decode()
        titles = re.findall(r"<item><title>(.*?)</title>", content)
        self.assertEqual(titles, [p.title for p in reversed(posts)][:20])
        self.assertIn("<link>http://localhost/blog/feed-post-21/</link>", content)
        self.assertIn("<category>Sites</category>", content)

    def test_render_without_images_and_no_dead_links(self):
        post = self.make_post("Plain post", datetime.date(2026, 3, 1), body_words=50)
        self.make_post("Second plain post", datetime.date(2026, 2, 1))
        for url in ("/blog/", post.url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'href="#"')
        # No feature image: the cards get the gradient stand-in, never an <img>.
        self.assertContains(self.client.get("/blog/"), 'class="blog-photo"', count=2)
        post_page = self.client.get(post.url)
        self.assertContains(post_page, '"@type": "BlogPosting"')
        self.assertContains(post_page, '<meta property="og:type" content="article">')
        self.assertContains(post_page, '<meta name="description" content="About Plain post.">')


class ReadingTimeTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()

    def test_minimum_one_and_scales(self):
        empty = self.make_post("Empty", datetime.date(2026, 1, 1))
        self.assertEqual(empty.reading_time, 1)
        self.assertEqual(self.make_post("220", datetime.date(2026, 1, 2), body_words=220).reading_time, 1)
        self.assertEqual(self.make_post("221", datetime.date(2026, 1, 3), body_words=221).reading_time, 2)
        self.assertEqual(self.make_post("1100", datetime.date(2026, 1, 4), body_words=1100).reading_time, 5)


class NavigationTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()
        self.about = AboutPage(title="Our Story", slug="our-story")
        self.home.add_child(instance=self.about)
        self.about.save_revision().publish()

    def _menus(self, path="/our-story/"):
        content = self.client.get(path).content.decode()
        main = re.search(r'<ul class="nav-list">.*?</nav>', content, re.S).group(0)
        mobile = re.search(r'<ul class="mobile-list">(?:(?!<ul class="mobile-list">).)*?</ul>\s*(?=</div>|<form)', content, re.S)
        return content, main, mobile.group(0) if mobile else ""

    def test_blog_link_follows_index_live_state(self):
        self.index.unpublish()
        content, main, mobile = self._menus()
        self.assertNotIn('href="/blog/"', main)
        self.assertNotIn('href="/blog/"', mobile)

        self.index.save_revision().publish()
        content, main, mobile = self._menus()
        self.assertIn('href="/blog/"', main)
        self.assertIn('href="/blog/"', mobile)

    def test_blog_sits_immediately_before_our_story(self):
        content, main, mobile = self._menus()
        for menu in (main, mobile):
            items = re.findall(r'<li[^>]*>\s*<a href="([^"]+)"', menu)
            self.assertIn("/blog/", items)
            self.assertEqual(items[items.index("/blog/") + 1], "/our-story/")

    def test_blog_is_current_on_index_category_and_post(self):
        post = self.make_post("A post", datetime.date(2026, 3, 1))
        for path in ("/blog/", "/blog/category/sites/", post.url):
            content, main, mobile = self._menus(path)
            self.assertIn('<li class="nav-item active">\n      <a href="/blog/" aria-current="page">Blog</a>', main)
        content, main, mobile = self._menus("/our-story/")
        self.assertNotIn('aria-current="page">Blog', main)


ACCOUNT_URLS = ["/pilgrims/my/photos/", "/pilgrims/feed/", "/pilgrims/notifications/"]


class AccountMenuTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()
        self.user = get_user_model().objects.create_user("pilgrim", "pilgrim@example.com", "pw")
        self.profile_url = f"/pilgrims/u/{self.user.pilgrim.handle}/"

    def _header(self, path="/blog/"):
        content = self.client.get(path).content.decode()
        header = re.search(r'<header class="site-header">.*?</header>', content, re.S).group(0)
        details = re.search(r'<details class="account-menu.*?</details>', header, re.S)
        return content, header, details.group(0) if details else None

    def test_signed_out_has_sign_in_and_no_account_menu(self):
        content, header, details = self._header()
        self.assertIn(">Sign in</a>", header)
        self.assertIsNone(details)
        self.assertNotIn("mobile-account", header)

    def test_signed_in_account_links_live_only_in_the_menu(self):
        self.client.force_login(self.user)
        content, header, details = self._header()
        self.assertIsNotNone(details)
        for url in ACCOUNT_URLS + [self.profile_url]:
            self.assertIn(f'href="{url}"', details)
        actions = re.search(r'<div class="header-actions">.*?<button class="nav-toggle"', header, re.S).group(0)
        outside = actions.replace(details, "")
        for url in ACCOUNT_URLS + [self.profile_url]:
            self.assertNotIn(f'href="{url}"', outside)
        self.assertNotIn(">Sign in</a>", header)
        self.assertIn(">My Passport &amp; Profile</a>", details)
        self.assertNotIn('href="/passport/"', header)

        mobile = re.search(r'<div class="mobile-account">.*?</div>', header, re.S).group(0)
        self.assertIn('aria-label="My account"', mobile)
        for url in ACCOUNT_URLS:
            self.assertIn(f'href="{url}"', mobile)
        self.assertLess(header.index('class="mobile-account"'), header.index('<ul class="mobile-list">\n'))

    def test_sign_out_is_a_post_form_with_csrf(self):
        self.client.force_login(self.user)
        content, header, details = self._header()
        for block in (details, header[header.index('class="mobile-signout"') - 7:]):
            form = re.search(r'<form[^>]*>.*?</form>', block, re.S).group(0)
            self.assertIn('method="post"', form)
            self.assertIn('action="/accounts/logout/"', form)
            self.assertIn('name="csrfmiddlewaretoken"', form)
        response = self.client.post("/accounts/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_trigger_is_current_on_account_pages_only(self):
        self.client.force_login(self.user)
        content, header, details = self._header("/pilgrims/feed/")
        self.assertIn('class="account-menu is-current"', details)
        self.assertIn('href="/pilgrims/feed/" aria-current="page"', details)
        content, header, details = self._header("/blog/")
        self.assertNotIn("is-current", details)
        self.assertNotIn('aria-current="page"', details)


class SearchSuggestTests(BlogFixtureMixin, WagtailPageTestCase):
    def setUp(self):
        self.make_site()

    def test_suggest_returns_blog_group(self):
        self.make_post("Lourdes in Winter", datetime.date(2026, 1, 1))
        data = self.client.get("/search/suggest.json?q=lourdes").json()
        groups = {g["key"]: g for g in data["groups"]}
        self.assertIn("blog", groups)
        self.assertEqual(groups["blog"]["label"], "Blog")
        self.assertEqual(groups["blog"]["results"][0]["title"], "Lourdes in Winter")

    def test_search_page_renders_blog_results(self):
        self.make_post("Lourdes in Winter", datetime.date(2026, 1, 1))
        response = self.client.get("/search/?query=lourdes&category=blog")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lourdes in Winter")


class MigrationStateTests(TestCase):
    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=StringIO())
        except SystemExit:
            self.fail(f"Missing migrations:\n{out.getvalue()}")
