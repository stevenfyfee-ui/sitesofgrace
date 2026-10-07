"""
Tests for home.SupportPage and its Stripe Checkout flow.

Stripe is never called for real: stripe.checkout.Session.create and
.retrieve are mocked everywhere they could be reached.
"""
import importlib
import logging
import os
import re
import sys
from unittest import mock

import stripe
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from home.models import HomePage, StorePage, SupportPage

FAKE_KEY = "sk_test_FAKEKEYabcd1234"
FAKE_PRODUCT = "prod_TESTSUPPORT"
CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_a1B2c3D4"
SESSION_ID = "cs_test_a1B2c3D4e5F6g7H8"
FICTITIOUS_EMAIL = "john.doe@example.com"

STRIPE_ON = override_settings(
    STRIPE_SECRET_KEY=FAKE_KEY, STRIPE_SUPPORT_PRODUCT_ID=FAKE_PRODUCT, SUPPORT_ENABLED=True,
)
STRIPE_OFF = override_settings(
    STRIPE_SECRET_KEY="", STRIPE_SUPPORT_PRODUCT_ID="", SUPPORT_ENABLED=False,
)

CREATE = "stripe.checkout.Session.create"
RETRIEVE = "stripe.checkout.Session.retrieve"

BANNED = ("donate", "donation", "charity")


def _session(**fields):
    """A real StripeObject (not a dict), like the library returns."""
    data = {
        "id": SESSION_ID,
        "status": "complete",
        "payment_status": "paid",
        "mode": "payment",
        "amount_total": 2500,
        "customer_details": {"email": FICTITIOUS_EMAIL, "name": "John Doe"},
    }
    data.update(fields)
    return stripe.checkout.Session.construct_from(data, FAKE_KEY)


class SupportTestCase(WagtailPageTestCase):
    def setUp(self):
        # The rate limiter lives in the cache; don't let one test's hits
        # count against the next.
        cache.clear()
        self.root = Page.get_first_root_node()
        # The migration-created "localhost" site is also flagged default;
        # make this test's site the only one, so "/contact/" means one place.
        Site.objects.update(is_default_site=False)
        Site.objects.create(hostname="testsite", root_page=self.root, is_default_site=True)
        self.homepage = HomePage(title="Home")
        self.root.add_child(instance=self.homepage)
        self.page = SupportPage(title="Support Sites of Grace")
        self.homepage.add_child(instance=self.page)

    def post(self, **data):
        return self.client.post(self.page.url, data)


# --- Structure, defaults, validation ---------------------------------------


class SupportPageStructureTests(SupportTestCase):
    def test_creatable_under_homepage_only(self):
        self.assertCanCreateAt(HomePage, SupportPage)
        self.assertCanNotCreateAt(StorePage, SupportPage)

    def test_max_count_one(self):
        self.assertFalse(SupportPage(title="Again").can_create_at(self.homepage))

    def test_new_page_defaults(self):
        fresh = SupportPage(title="Anything")
        self.assertEqual(fresh.slug, "support")
        self.assertTrue(fresh.search_description.startswith("Sites of Grace is free for every pilgrim."))
        self.assertEqual(fresh.hero_title, "Help Keep the Way Open")
        self.assertEqual(fresh.preset_list, [5, 10, 25, 50])
        self.assertEqual(
            [b.value["title"] for b in fresh.helps],
            ["Hosting & Upkeep", "Research", "Maps & Photography", "New Pilgrimage Guides"],
        )
        self.assertEqual(len(fresh.faqs), 5)
        self.assertEqual(len(fresh.ways), 4)

    def test_suggest_item_unlinked_without_a_contact_page(self):
        text = str(list(SupportPage(title="x").ways)[1].value["text"])
        self.assertNotIn("<a", text)
        self.assertIn("Tell us about a place", text)

    def test_suggest_item_links_to_a_live_contact_page(self):
        self.root.add_child(instance=Page(title="Contact", slug="contact"))
        text = str(list(SupportPage(title="x").ways)[1].value["text"])
        self.assertIn('?topic=suggest">Tell us</a>', text)


class SupportPageCleanTests(SupportTestCase):
    def assertCleanError(self, field, **changes):
        for name, value in changes.items():
            setattr(self.page, name, value)
        with self.assertRaises(ValidationError) as ctx:
            self.page.clean()
        self.assertIn(field, ctx.exception.message_dict)

    def test_defaults_are_valid(self):
        self.page.clean()

    def test_blank_disclaimer_rejected(self):
        self.assertCleanError("disclaimer", disclaimer="   ")

    def test_disclaimer_without_phrase_rejected(self):
        self.assertCleanError("disclaimer", disclaimer="Contributions are voluntary.")

    def test_presets_validated(self):
        self.assertCleanError("preset_amounts", preset_amounts="5,ten")
        self.assertCleanError("preset_amounts", preset_amounts="5,10,15,20,25,30,35")
        self.assertCleanError("preset_amounts", preset_amounts="2,10")

    def test_defaults_must_be_presets(self):
        self.assertCleanError("default_amount_once", preset_amounts="5,25,50", default_amount_monthly=5)


# --- Rendering --------------------------------------------------------------


@STRIPE_ON
class SupportPageRenderTests(SupportTestCase):
    def test_renders_200_with_defaults_and_no_images(self):
        self.assertPageIsRenderable(self.page)
        response = self.client.get(self.page.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/support_page.html")
        content = response.content.decode()
        self.assertIn("support-photo", content)
        self.assertIn("data-support-form", content)
        self.assertNotIn('href="#"', content)
        self.assertNotIn("Photo:", content)
        self.assertNotIn('name="robots"', content)

    def test_empty_optional_fields_leave_no_wrappers(self):
        for field in (
            "hero_eyebrow", "hero_intro", "why_eyebrow", "why_heading", "why_body",
            "pull_quote", "pull_quote_cite", "helps_eyebrow", "give_heading", "give_lede",
            "ways_heading", "ways_intro", "free_card_heading", "free_card_text",
            "faq_eyebrow", "faq_heading",
        ):
            setattr(self.page, field, "")
        self.page.helps = []
        self.page.ways = []
        self.page.faqs = []
        self.page.save_revision().publish()

        content = self.client.get(self.page.url).content.decode()
        for wrapper in (
            "support-eyebrow", "support-hero-intro", "support-why", "support-helps",
            "support-pull", "support-lede", "support-side", "support-faq",
        ):
            self.assertNotIn(wrapper, content)
        self.assertNotIn("<h2></h2>", content)
        self.assertIn("data-support-form", content)  # the form itself always renders

    def test_cache_control_on_get(self):
        response = self.client.get(self.page.url)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_manage_links_only_when_set(self):
        content = self.client.get(self.page.url).content.decode()
        self.assertNotIn("Manage monthly support", content)
        self.assertNotIn("Manage your monthly support", content)

        self.page.manage_url = "https://billing.stripe.com/p/login/test_example"
        self.page.save_revision().publish()
        content = self.client.get(self.page.url).content.decode()
        self.assertIn("Manage monthly support", content)
        self.assertIn("Manage your monthly support", content)


@STRIPE_OFF
class SupportDisabledTests(SupportTestCase):
    def test_soon_panel_instead_of_form(self):
        response = self.client.get(self.page.url)
        self.assertContains(response, "Online Support Opens Soon")
        self.assertNotContains(response, "data-support-form")
        self.assertNotContains(response, 'name="amount"')
        # The rest of the page is unchanged.
        self.assertContains(response, "Other Ways to Help")
        self.assertContains(response, "Common Questions")

    @mock.patch(CREATE)
    def test_post_makes_no_stripe_call(self, create):
        response = self.post(frequency="once", amount="25")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Online Support Opens Soon")
        create.assert_not_called()
        self.assertEqual(response["Cache-Control"], "private, no-store")

    @mock.patch(RETRIEVE)
    def test_thanks_query_makes_no_stripe_call(self, retrieve):
        response = self.client.get(self.page.url, {"thanks": "1", "session_id": SESSION_ID})
        retrieve.assert_not_called()
        self.assertNotContains(response, "data-support-thanks")


# --- Checkout ---------------------------------------------------------------


@STRIPE_ON
class SupportCheckoutTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch(CREATE, return_value=mock.Mock(url=CHECKOUT_URL))
        self.create = patcher.start()
        self.addCleanup(patcher.stop)

    def kwargs(self):
        self.create.assert_called_once()
        return self.create.call_args.kwargs

    def test_once_25(self):
        response = self.post(frequency="once", amount="25")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], CHECKOUT_URL)
        self.assertEqual(response["Cache-Control"], "private, no-store")

        kw = self.kwargs()
        self.assertEqual(kw["api_key"], FAKE_KEY)
        self.assertEqual(kw["mode"], "payment")
        self.assertEqual(kw["submit_type"], "pay")
        item = kw["line_items"][0]
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["price_data"], {
            "currency": "usd", "product": FAKE_PRODUCT, "unit_amount": 2500,
        })
        self.assertEqual(
            kw["custom_text"]["submit"]["message"],
            "Sites of Grace is not a 501(c)(3) charitable organization. "
            "Contributions are voluntary and are not tax-deductible.",
        )
        self.assertEqual(kw["metadata"], {"source": "support_page", "frequency": "once"})
        full_url = self.page.get_full_url()
        self.assertEqual(kw["success_url"], full_url + "?thanks=1&session_id={CHECKOUT_SESSION_ID}")
        self.assertEqual(kw["cancel_url"], full_url + "#give")
        self.assertNotIn("customer_email", kw)

    def test_monthly_10(self):
        response = self.post(frequency="monthly", amount="10")
        self.assertEqual(response.status_code, 303)
        kw = self.kwargs()
        self.assertEqual(kw["mode"], "subscription")
        self.assertEqual(kw["line_items"][0]["price_data"]["recurring"], {"interval": "month"})
        self.assertEqual(kw["line_items"][0]["price_data"]["unit_amount"], 1000)
        self.assertNotIn("submit_type", kw)
        self.assertEqual(kw["metadata"]["frequency"], "monthly")

    def test_signed_in_user_email_never_sent(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username="johndoe", email=FICTITIOUS_EMAIL, password="x-not-real-x",
        )
        self.client.force_login(user)
        self.post(frequency="once", amount="10")
        self.assertNotIn(FICTITIOUS_EMAIL, repr(self.kwargs()))

    def test_custom_7_50(self):
        response = self.post(frequency="once", amount="other", custom_amount="7.50")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.kwargs()["line_items"][0]["price_data"]["unit_amount"], 750)

    def test_invalid_amounts_rejected_without_stripe_call(self):
        for custom in ("2.99", "1000.01", "abc", "1e3", "-5", "7.505"):
            with self.subTest(custom=custom):
                response = self.post(frequency="once", amount="other", custom_amount=custom)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'role="alert"')
                # The visitor's choice comes back.
                self.assertContains(response, f'value="{custom}"')
                self.assertRegex(response.content.decode(), r'value="other" checked')
        for amount in ("7", "", "other"):
            with self.subTest(amount=amount):
                response = self.post(frequency="once", amount=amount)
                self.assertContains(response, 'role="alert"')
        self.create.assert_not_called()

    def test_frequency_validated(self):
        response = self.post(frequency="weekly", amount="10")
        self.assertContains(response, 'role="alert"')
        self.page.allow_monthly = False
        self.page.save_revision().publish()
        response = self.post(frequency="monthly", amount="10")
        self.assertContains(response, 'role="alert"')
        self.create.assert_not_called()

    def test_error_preserves_frequency(self):
        response = self.post(frequency="monthly", amount="other", custom_amount="abc")
        self.assertRegex(response.content.decode(), r'value="monthly" checked')

    def test_ninth_post_in_ten_minutes_refused(self):
        for _ in range(8):
            self.assertEqual(self.post(frequency="once", amount="10").status_code, 303)
        response = self.post(frequency="once", amount="10")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please wait a few minutes and try again.")
        self.assertEqual(self.create.call_count, 8)

    def test_rate_limit_is_per_ip(self):
        for _ in range(9):
            self.client.post(self.page.url, {"frequency": "once", "amount": "10"}, REMOTE_ADDR="10.0.0.1")
        response = self.client.post(
            self.page.url, {"frequency": "once", "amount": "10"}, REMOTE_ADDR="10.0.0.2",
        )
        self.assertEqual(response.status_code, 303)

    def test_stripe_error_is_friendly_logged_and_keyless(self):
        self.create.side_effect = stripe.AuthenticationError(
            f"Invalid API Key provided: sk_test_****{FAKE_KEY[-4:]}"
        )
        with self.assertLogs("home.support", level="ERROR") as logs:
            response = self.post(frequency="once", amount="25")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "We couldn&#x27;t reach our payment provider. Please try again in a moment.",
        )
        self.assertRegex(response.content.decode(), r'value="25" checked')
        formatted = "\n".join(logging.Formatter().format(r) for r in logs.records)
        self.assertIn("AuthenticationError", formatted)
        for secret in ("sk_test", FAKE_KEY, FAKE_KEY[-4:]):
            self.assertNotIn(secret, formatted)

    def test_timeout_is_friendly(self):
        self.create.side_effect = stripe.APIConnectionError("Request timed out")
        with self.assertLogs("home.support", level="ERROR"):
            response = self.post(frequency="monthly", amount="5")
        self.assertContains(response, "reach our payment provider")


# --- Thank-you --------------------------------------------------------------


@STRIPE_ON
class SupportThanksTests(SupportTestCase):
    def get_thanks(self, session_id=SESSION_ID):
        return self.client.get(self.page.url, {"thanks": "1", "session_id": session_id})

    @mock.patch(RETRIEVE)
    def test_complete_session_shows_thanks(self, retrieve):
        retrieve.return_value = _session()
        response = self.get_thanks()
        retrieve.assert_called_once()
        self.assertEqual(retrieve.call_args.args[0], SESSION_ID)
        self.assertEqual(retrieve.call_args.kwargs["api_key"], FAKE_KEY)
        self.assertContains(response, "$25.00 · one time")
        self.assertContains(response, 'role="status"')
        self.assertContains(response, '<meta name="robots" content="noindex">')
        self.assertNotContains(response, "data-support-form")
        self.assertNotContains(response, FICTITIOUS_EMAIL)
        self.assertNotContains(response, "John Doe")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    @mock.patch(RETRIEVE)
    def test_monthly_session(self, retrieve):
        retrieve.return_value = _session(mode="subscription", amount_total=500)
        self.assertContains(self.get_thanks(), "$5.00 · monthly")

    @mock.patch(RETRIEVE)
    def test_open_session_shows_normal_page(self, retrieve):
        retrieve.return_value = _session(status="open", payment_status="unpaid")
        response = self.get_thanks()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-support-thanks")
        self.assertContains(response, "data-support-form")
        self.assertNotContains(response, 'role="alert"')
        self.assertNotContains(response, 'name="robots"')

    @mock.patch(RETRIEVE)
    def test_bad_ids_never_reach_stripe(self, retrieve):
        for bad in ("abc", "cs_" + "a" * 500, "cs_", "cs_test_<script>", ""):
            with self.subTest(session_id=bad[:20]):
                response = self.get_thanks(bad)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "data-support-thanks")
        retrieve.assert_not_called()

    @mock.patch(RETRIEVE, side_effect=stripe.InvalidRequestError("No such checkout.session", "id"))
    def test_retrieve_error_shows_normal_page(self, retrieve):
        with self.assertLogs("home.support", level="ERROR"):
            response = self.get_thanks()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-support-thanks")
        self.assertNotContains(response, 'role="alert"')


# --- Footer link, home band, and wording --------------------------------------


@STRIPE_OFF
class SupportLinksTests(SupportTestCase):
    def home_html(self):
        return self.client.get(self.homepage.url).content.decode()

    def test_absent_while_draft(self):
        self.page.unpublish()
        html = self.home_html()
        self.assertNotIn("footer-support", html)
        self.assertNotIn("support-band", html)

    def test_present_once_live_even_before_stripe(self):
        html = self.home_html()
        self.assertIn(f'class="footer-support" href="{self.page.url}"', html)
        self.assertIn('class="support-band"', html)
        self.assertIn("independently built and free for every pilgrim", html)
        band = html[html.index('class="support-band"'):html.index("</section>", html.index('class="support-band"'))]
        self.assertNotIn("<form", band)
        self.assertNotIn("$", band)

    def test_band_hidden_by_toggle_footer_stays(self):
        self.page.show_home_band = False
        self.page.save_revision().publish()
        html = self.home_html()
        self.assertNotIn("support-band", html)
        self.assertIn("footer-support", html)

    def test_band_only_on_home_page(self):
        html = self.client.get(self.page.url).content.decode()
        self.assertNotIn('class="support-band"', html)
        self.assertIn("footer-support", html)

    def test_never_in_header_or_menus(self):
        html = self.home_html()
        header = html[: html.index('<main id="content">')]
        self.assertNotIn(self.page.url, header)
        self.assertNotIn("Support", header)


class SupportWordingTests(SupportTestCase):
    """No rendered page uses the banned words, and "tax-deductible" appears
    only in the disclaimer and the FAQ."""

    def assertClean(self, html):
        lowered = html.lower()
        for word in BANNED:
            self.assertNotIn(word, lowered)
        outside = re.sub(r'<p class="support-fine">.*?</p>', "", html, flags=re.S)
        outside = re.sub(r'<section class="support-faq">.*?</section>', "", outside, flags=re.S)
        self.assertNotIn("tax-deductible", outside.lower())

    def test_support_page_all_states(self):
        with STRIPE_OFF:
            self.assertClean(self.client.get(self.page.url).content.decode())
        with STRIPE_ON:
            html = self.client.get(self.page.url).content.decode()
            self.assertIn("not tax-deductible", html)
            self.assertClean(html)
            with mock.patch(RETRIEVE, return_value=_session()):
                self.assertClean(self.get_thanks_html())

    def get_thanks_html(self):
        return self.client.get(
            self.page.url, {"thanks": "1", "session_id": SESSION_ID},
        ).content.decode()

    def test_home_page_and_footer(self):
        self.assertClean(self.client.get(self.homepage.url).content.decode())


# --- Production settings ------------------------------------------------------


class ProductionStripeWarningTests(SimpleTestCase):
    """settings/production.py warns at startup about a test-mode key."""

    MODULES = ("sitesofgrace.settings.base", "sitesofgrace.settings.production")

    def import_production(self, stripe_key):
        env = {
            "SECRET_KEY": "test-only-not-a-real-secret",
            "DATABASE_URL": "postgres://user:pass@localhost:5432/example",
            "STRIPE_SECRET_KEY": stripe_key,
            "STRIPE_SUPPORT_PRODUCT_ID": FAKE_PRODUCT,
        }
        # base.py reads STRIPE_SECRET_KEY at import, so both modules are
        # imported fresh under this environment, then put back as they were.
        saved = {name: sys.modules.pop(name, None) for name in self.MODULES}
        try:
            with mock.patch.dict(os.environ, env):
                return importlib.import_module("sitesofgrace.settings.production")
        finally:
            for name, module in saved.items():
                sys.modules.pop(name, None)
                if module is not None:
                    sys.modules[name] = module

    def test_test_key_logs_a_warning_without_the_key(self):
        with self.assertLogs("sitesofgrace.settings.production", level="WARNING") as logs:
            prod = self.import_production(FAKE_KEY)
        self.assertFalse(prod.DEBUG)
        stripe_warnings = [r for r in logs.records if "STRIPE_SECRET_KEY" in r.getMessage()]
        self.assertEqual(len(stripe_warnings), 1)
        self.assertEqual(stripe_warnings[0].levelname, "WARNING")
        formatted = "\n".join(logging.Formatter().format(r) for r in logs.records)
        for secret in (FAKE_KEY, FAKE_KEY[-4:]):
            self.assertNotIn(secret, formatted)

    def test_live_key_logs_no_stripe_warning(self):
        logger = logging.getLogger("sitesofgrace.settings.production")
        with mock.patch.object(logger, "warning") as warning:
            self.import_production("sk_live_FAKEKEYabcd1234")
        self.assertFalse(
            any("STRIPE_SECRET_KEY" in str(call.args[0]) for call in warning.call_args_list)
        )
