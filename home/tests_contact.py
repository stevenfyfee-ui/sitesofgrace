"""
Tests for home.ContactPage's structure and rendering. The form itself is
tested in contact/tests.py.
"""
from datetime import date

from wagtail.test.utils import WagtailPageTestCase

from contact.tests import ContactTestCase
from home.models import ContactPage, HomePage, LegalDetails, LegalNotices, LegalPage


class ContactPageStructureTests(ContactTestCase, WagtailPageTestCase):
    def test_creatable_under_homepage_only(self):
        self.assertCanCreateAt(HomePage, ContactPage)
        self.assertCanNotCreateAt(ContactPage, ContactPage)
        self.assertEqual(ContactPage.max_count, 1)

    def test_new_page_defaults(self):
        page = ContactPage(title="Contact")
        self.assertEqual(page.slug, "contact")
        self.assertTrue(page.search_description.startswith("Questions, corrections, site suggestions"))
        self.assertEqual([b.value["topic"] for b in page.topic_cards],
                         ["question", "suggest", "correction", "pilgrimage", "partner", "prayer"])
        self.assertEqual(len(page.faqs), 5)


class ContactPageRenderTests(ContactTestCase):
    def test_renders_with_defaults_and_no_images(self):
        response = self.client.get(self.page.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/contact_page.html")
        for text in (
            "We&#x27;d Love to Hear From You", "Choose a Topic to Get Started", "Send Us a Message",
            "Other Ways to Reach Us", "Planning a Visit?", "A note on who we are.", "Common Questions",
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'class="contact-photo"')
        # All eight topics in the select, whatever the cards show.
        self.assertEqual(response.content.decode().count("<option value="), 8)
        self.assertContains(response, 'href="/home-test/contact/?topic=prayer#contact-form"')
        self.assertContains(response, 'name="website"')
        self.assertContains(response, "Leave this field empty")

    def test_blank_email_hides_the_row(self):
        response = self.client.get(self.page.url)
        self.assertNotContains(response, "mailto:")
        details = LegalDetails.load()
        details.contact_email = "hello@example.com"
        details.save()
        self.assertContains(self.client.get(self.page.url), 'href="mailto:hello@example.com"')

    def test_empty_copy_leaves_no_wrapper(self):
        self.page.topics_eyebrow = self.page.topics_heading = ""
        self.page.topic_cards = []
        self.page.faqs = []
        self.page.save_revision().publish()
        response = self.client.get(self.page.url)
        self.assertNotContains(response, "contact-topics")
        self.assertNotContains(response, "contact-faq")

    def test_contact_legal_notice_renders(self):
        response = self.client.get(self.page.url)
        self.assertContains(response, "We use your name and email only to reply to you.")
        # The Privacy Policy isn't live, so its name is plain text.
        self.assertNotContains(response, 'href="/privacy-policy/"')
        self.assertTrue(LegalNotices._meta.get_field("contact_legal").default.endswith(
            "[Privacy Policy](/privacy-policy/)."
        ))

    def test_policy_links_only_for_live_legal_pages(self):
        response = self.client.get(self.page.url)
        self.assertNotContains(response, "contact-policy-links")
        self.homepage.add_child(instance=LegalPage(
            title="Privacy Policy", slug="privacy-policy", effective_date=date(2026, 10, 22),
            body="<p>Text.</p>",
        ))
        response = self.client.get(self.page.url)
        self.assertContains(response, "contact-policy-links")
        self.assertContains(response, '<span><a href="/home-test/privacy-policy/">Privacy Policy</a></span>')
        # The contact_legal notice links it too, now that it's live.
        self.assertContains(response, 'See our <a href="/home-test/privacy-policy/">Privacy Policy</a>.')
        self.assertNotContains(response, "Copyright &amp; Content Policy</a>")
        self.assertNotContains(response, "Accessibility</a>")

    def test_billing_note(self):
        response = self.client.get(self.page.url + "?topic=billing")
        self.assertContains(response, "Please don&#x27;t include card numbers.")
        self.assertNotContains(response, "Support &amp; Billing Notice</a>")
        self.homepage.add_child(instance=LegalPage(
            title="Support & Billing Notice", slug="support-and-billing",
            effective_date=date(2026, 10, 22), body="<p>Text.</p>",
        ))
        self.assertContains(self.client.get(self.page.url + "?topic=billing"), "Support &amp; Billing Notice</a>")

    def test_prayer_note_shown_for_prayer_topic(self):
        hidden = self.client.get(self.page.url).content.decode()
        self.assertIn("data-contact-prayer hidden", hidden)
        shown = self.client.get(self.page.url + "?topic=prayer").content.decode()
        self.assertNotIn("data-contact-prayer hidden", shown)
        self.assertIn("Your intention", shown)
