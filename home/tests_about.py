from home.models import AboutPage, HomePage, StorePage

from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase


class AboutPageStructureTests(WagtailPageTestCase):
    """AboutPage's placement in the page tree."""

    def setUp(self):
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)

    def test_creatable_under_homepage(self):
        self.assertCanCreateAt(HomePage, AboutPage)

    def test_not_creatable_under_other_pages(self):
        self.assertCanNotCreateAt(StorePage, AboutPage)

    def test_max_count_one(self):
        self.homepage.add_child(instance=AboutPage(title="Our Story"))
        second = AboutPage(title="Our Story Again")
        self.assertFalse(second.can_create_at(self.homepage))


class AboutPageDefaultCopyTests(WagtailPageTestCase):
    """A page created with no arguments carries all the launch copy."""

    def setUp(self):
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)
        self.about = AboutPage(title="Our Story")
        self.homepage.add_child(instance=self.about)
        self.about.refresh_from_db()

    def test_hero_copy_prefilled(self):
        self.assertEqual(
            self.about.hero_title,
            "Helping People Discover the Places Where Faith Comes Alive",
        )
        self.assertEqual(self.about.hero_cta_label, "Explore Sacred Sites")

    def test_founder_copy_prefilled(self):
        self.assertEqual(self.about.founder_name, "Steven Fyffe")
        self.assertEqual(self.about.founder_role, "Founder, Sites of Grace")

    def test_pillars_prefilled(self):
        pillars = list(self.about.pillars)
        self.assertEqual(len(pillars), 4)
        self.assertEqual(
            [p.value["title"] for p in pillars],
            ["Discover", "Learn", "Prepare", "Remember"],
        )

    def test_becoming_cards_prefilled(self):
        cards = list(self.about.becoming_cards)
        self.assertEqual(len(cards), 3)
        self.assertEqual(
            [c.value["title"] for c in cards],
            ["Explore Sacred Places", "Plan Your Pilgrimage", "Create Your Pilgrim Story"],
        )

    def test_slug_defaults_to_our_story(self):
        fresh = AboutPage(title="Whatever Steven Types")
        self.assertEqual(fresh.slug, "our-story")


class AboutPageRenderTests(WagtailPageTestCase):
    """The page must look finished before any image is uploaded."""

    def setUp(self):
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)
        self.about = AboutPage(title="Our Story")
        self.homepage.add_child(instance=self.about)

    def test_renders_200_with_no_images(self):
        self.assertPageIsRenderable(self.about)
        response = self.client.get(self.about.url)
        self.assertEqual(response.status_code, 200)

    def test_no_placeholder_or_dead_links(self):
        response = self.client.get(self.about.url)
        content = response.content.decode()
        self.assertNotIn("Photo:", content)
        self.assertNotIn('href="#"', content)

    def test_template_used(self):
        response = self.client.get(self.about.url)
        self.assertTemplateUsed(response, "home/about_page.html")


class OurStoryNavLinkTests(WagtailPageTestCase):
    """The header/footer "Our Story" link only appears once the page is live."""

    def setUp(self):
        root_page = Page.get_first_root_node()
        Site.objects.create(hostname="testsite", root_page=root_page, is_default_site=True)
        self.homepage = HomePage(title="Home")
        root_page.add_child(instance=self.homepage)
        self.about = AboutPage(title="Our Story")
        self.homepage.add_child(instance=self.about)

    def test_link_absent_while_draft(self):
        self.about.live = False
        self.about.save()
        response = self.client.get(self.homepage.url)
        self.assertNotContains(response, ">Our Story<")

    def test_link_present_once_live(self):
        response = self.client.get(self.homepage.url)
        self.assertContains(response, f'href="{self.about.url}"')
        self.assertContains(response, ">Our Story<")
