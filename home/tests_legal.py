"""
Tests for the legal pages, their settings and notices, the footer's legal
column, and the policy-driven fixes that shipped with them.

All Legal details values here are obvious fakes (John Doe, 123 Main St,
legal@example.com).
"""
import datetime
import re
from io import StringIO
from unittest import mock

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from home import legal, support
from home.models import HomePage, LegalDetails, LegalNotices, LegalPage, SupportPage

CONTENT_DIR = settings.BASE_DIR / "legal" / "content"

EXPECTED_TITLES = {
    "privacy-policy": "Privacy Policy",
    "terms-of-use": "Terms of Use",
    "affiliate-disclosure": "Affiliate & Advertising Disclosure",
    "travel-disclaimer": "Travel & Pilgrimage Disclaimer",
    "catholic-content-notice": "Catholic Content, Church Status & Testimony Notice",
    "community-policy": "Community, Photos & User Content Policy",
    "copyright-policy": "Copyright & Content Policy",
    "support-and-billing": "Support Payments & Recurring Billing Notice",
    "cookie-notice": "Cookies & Tracking Notice",
    "accessibility": "Accessibility Statement",
}

FAKE_DETAILS = {
    "operator_name": "John Doe",
    "contact_email": "legal@example.com",
    "mailing_address": "123 Main St\nAnytown, CA 90000",
    "dmca_agent_name": "John Doe",
    "dmca_agent_address": "123 Main St, Anytown, CA 90000",
    "dmca_agent_phone": "555-0100",
    "dmca_agent_email": "legal@example.com",
}


def fill_details(**overrides):
    details = LegalDetails.load()
    for name, value in {**FAKE_DETAILS, **overrides}.items():
        setattr(details, name, value)
    details.save()
    return details


class LegalSiteTestCase(WagtailPageTestCase):
    def setUp(self):
        cache.clear()
        self.root = Page.get_first_root_node()
        Site.objects.update(is_default_site=False)
        self.site = Site.objects.create(hostname="testsite", root_page=self.root, is_default_site=True)
        self.homepage = HomePage(title="Home")
        self.root.add_child(instance=self.homepage)
        Site.objects.filter(pk=self.site.pk).update(root_page=self.homepage)
        self.site.refresh_from_db()

    def tearDown(self):
        # Wagtail caches site root paths; don't leave this test's sites
        # behind for the next test class.
        cache.clear()
        super().tearDown()

    def run_command(self, *args):
        out = StringIO()
        call_command("create_legal_pages", *args, stdout=out)
        return out.getvalue()

    def publish(self, slug):
        page = LegalPage.objects.get(slug=slug)
        page.get_latest_revision().publish()
        return LegalPage.objects.get(slug=slug)


# --- Content in the repo ----------------------------------------------------


class ContentFileTests(SimpleTestCase):
    def all_files(self):
        return sorted(CONTENT_DIR.glob("*.md"))

    def test_ten_pages_plus_notices_and_nothing_else(self):
        names = {p.name for p in self.all_files()}
        self.assertEqual(names, {f"{slug}.md" for slug in legal.LEGAL_SLUGS} | {"notices.md"})

    def test_no_build_time_slots_or_placeholder_brackets_remain(self):
        for path in self.all_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertNotRegex(text, r"\{\{\s*(AUDIT|CHOOSE)")
                self.assertNotRegex(text, r"\[[A-Z][A-Z0-9 _:-]{2,}\]")
                # Every {{...}} left is a known runtime token.
                legal.tokens_in(text)

    def test_titles_come_from_the_first_line(self):
        for slug, title in EXPECTED_TITLES.items():
            text = (CONTENT_DIR / f"{slug}.md").read_text(encoding="utf-8")
            self.assertEqual(legal.parse_content_file(text)[0], title)

    def test_notice_fields_match_notices_md(self):
        notices = legal.parse_notices((CONTENT_DIR / "notices.md").read_text(encoding="utf-8"))
        fields = {
            f.name: f.default for f in LegalNotices._meta.get_fields()
            if f.concrete and f.name not in ("id",)
        }
        self.assertEqual(set(fields), set(notices))
        for key, text in notices.items():
            self.assertEqual(fields[key], text, key)


# --- Token filling and notice rendering --------------------------------------


class TokenTests(SimpleTestCase):
    def details(self, **values):
        return LegalDetails(**{**FAKE_DETAILS, **values})

    def test_unknown_token_raises(self):
        with self.assertRaises(legal.UnknownTokenError):
            legal.fill_tokens("Write to {{NOT_A_TOKEN}}.", self.details())
        with self.assertRaises(legal.UnknownTokenError):
            legal.render_notice("{{CHOOSE:EXIF}}", self.details(), {})

    def test_values_are_escaped_and_emails_become_mailto_links(self):
        html = legal.fill_tokens(
            "{{OPERATOR_NAME}} at {{CONTACT_EMAIL}}",
            self.details(operator_name='John <script>alert("x")</script> Doe'),
        )
        self.assertNotIn("<script>", html)
        self.assertIn("John &lt;script&gt;", html)
        self.assertIn('<a href="mailto:legal@example.com">legal@example.com</a>', html)

    def test_blank_value_renders_empty_and_logs(self):
        with self.assertLogs("home.legal", level="WARNING"):
            html = legal.fill_tokens("Email {{CONTACT_EMAIL}}.", self.details(contact_email=""))
        self.assertEqual(html, "Email .")

    def test_notice_escapes_first_then_bold_and_links(self):
        html = legal.render_notice(
            "**Hi** <b>raw</b> [Site](https://example.com/) [Bad](javascript:alert(1))",
            self.details(), {},
        )
        self.assertIn("<strong>Hi</strong>", html)
        self.assertIn("&lt;b&gt;raw&lt;/b&gt;", html)
        self.assertIn('<a href="https://example.com/">Site</a>', html)
        self.assertNotIn('href="javascript', html)

    def test_legal_links_in_notices_only_when_live(self):
        text = "See our [Privacy Policy](/privacy-policy/)."
        self.assertEqual(legal.render_notice(text, self.details(), {}), "See our Privacy Policy.")
        self.assertIn(
            '<a href="/privacy-policy/">Privacy Policy</a>',
            legal.render_notice(text, self.details(), {"privacy-policy": "/privacy-policy/"}),
        )

    def test_amount_placeholder(self):
        html = legal.render_notice("Charged {amount} monthly.", self.details(), {}, amount="$5")
        self.assertIn('<span data-notice-amount>$5</span>', html)
        self.assertEqual(
            legal.notice_plain("**Charged** {amount}. [Support](/support/)", self.details(), amount="$5.00"),
            "Charged $5.00. Support",
        )

    def test_markdown_subset(self):
        html = legal.markdown_to_richtext(
            "Intro **bold** *it* [a](/x/).\n\n## Head\nPara one\n\n- one\n- two\n\n1. first\n2. second\n### Sub"
        )
        self.assertEqual(
            html,
            '<p>Intro <b>bold</b> <i>it</i> <a href="/x/">a</a>.</p><h2>Head</h2><p>Para one</p>'
            "<ul><li>one</li><li>two</li></ul><ol><li>first</li><li>second</li></ol><h3>Sub</h3>",
        )


# --- create_legal_pages ---------------------------------------------------------


class CreateLegalPagesTests(LegalSiteTestCase):
    def test_creates_ten_unpublished_drafts(self):
        out = self.run_command("--effective", "2026-11-01")
        pages = {p.slug: p for p in LegalPage.objects.child_of(self.homepage)}
        self.assertEqual(set(pages), set(legal.LEGAL_SLUGS))
        for slug, page in pages.items():
            with self.subTest(slug):
                self.assertEqual(page.title, EXPECTED_TITLES[slug])
                self.assertFalse(page.live)
                self.assertEqual(page.effective_date, datetime.date(2026, 11, 1))
                self.assertIsNotNone(page.latest_revision)
                self.assertNotIn("{{", page.search_description)
                self.assertTrue(page.search_description)
        self.assertIn("Created (draft): privacy-policy", out)
        # The first paragraph without a token: the Privacy Policy skips its
        # "Operator: {{OPERATOR_NAME}}" line.
        self.assertTrue(
            pages["privacy-policy"].search_description.startswith("Sites of Grace operates SitesOfGrace.com"),
            pages["privacy-policy"].search_description,
        )

    def test_search_description_skips_paragraphs_with_tokens(self):
        self.assertEqual(
            legal.first_paragraph_text("**Operator:** {{OPERATOR_NAME}}, here.\n\n## 1. Who\nPlain **text** [x](/y/)."),
            "Plain text x.",
        )

    def test_monthly_text_is_trimmed_to_stripes_limit(self):
        notices = LegalNotices.load()
        notices.stripe_monthly_submit = "Charged {amount}. " + "x" * 1500
        notices.save()
        message = support.monthly_submit_message(500)
        self.assertEqual(len(message), support.STRIPE_SUBMIT_MESSAGE_MAX)
        self.assertTrue(message.startswith(support.CHECKOUT_SUBMIT_MESSAGE))

    def test_rerun_does_nothing(self):
        self.run_command()
        revisions = {p.slug: p.latest_revision_id for p in LegalPage.objects.all()}
        out = self.run_command()
        self.assertEqual(revisions, {p.slug: p.latest_revision_id for p in LegalPage.objects.all()})
        self.assertIn("Created (draft): none", out)
        self.assertIn("Skipped (already exists): privacy-policy", out)

    def test_update_makes_a_new_draft_and_leaves_live_alone(self):
        self.run_command("--effective", "2026-11-01")
        fill_details()
        page = LegalPage.objects.get(slug="privacy-policy")
        page.body = "<p>The live text.</p>"
        page.save_revision().publish()
        live_revision = LegalPage.objects.get(slug="privacy-policy").live_revision_id

        self.run_command("--update", "--effective", "2026-12-01")

        page = LegalPage.objects.get(slug="privacy-policy")
        self.assertTrue(page.live)
        self.assertEqual(page.live_revision_id, live_revision)
        self.assertEqual(page.body, "<p>The live text.</p>")
        self.assertEqual(page.effective_date, datetime.date(2026, 11, 1))
        self.assertTrue(page.has_unpublished_changes)
        draft = page.get_latest_revision_as_object()
        self.assertEqual(draft.effective_date, datetime.date(2026, 12, 1))
        self.assertIn("Who we are", draft.body)

    def test_live_old_privacy_page_stops_the_command(self):
        old = LegalPage(title="Privacy", slug="privacy", effective_date=datetime.date(2026, 10, 8),
                        body="<p>Old.</p>")
        self.homepage.add_child(instance=old)
        old.save_revision().publish()
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertFalse(LegalPage.objects.filter(slug="privacy-policy").exists())
        self.assertTrue(LegalPage.objects.get(slug="privacy").live)

    def test_draft_old_slugs_are_moved_and_redirected(self):
        for slug in ("privacy", "terms"):
            self.homepage.add_child(instance=LegalPage(
                title=slug.title(), slug=slug, live=False,
                effective_date=datetime.date(2026, 10, 8), body="<p>Old.</p>",
            ))
        old_ids = set(LegalPage.objects.values_list("pk", flat=True))
        self.run_command()
        moved = LegalPage.objects.filter(pk__in=old_ids)
        self.assertEqual({p.slug for p in moved}, {"privacy-policy", "terms-of-use"})

        from wagtail.contrib.redirects.models import Redirect

        redirect = Redirect.objects.get(old_path="/privacy")
        self.assertTrue(redirect.is_permanent)
        self.assertEqual(redirect.redirect_page.slug, "privacy-policy")
        self.assertTrue(Redirect.objects.filter(old_path="/terms").exists())


# --- Publishing guard and rendering ------------------------------------------------


class PublishGuardTests(LegalSiteTestCase):
    def setUp(self):
        super().setUp()
        self.run_command()
        self.admin = get_user_model().objects.create_superuser(
            "legal_admin", "john.doe@example.com", "pw"
        )
        self.client.force_login(self.admin)
        self.page = LegalPage.objects.get(slug="privacy-policy")

    def post_edit(self, action):
        data = {
            "title": self.page.title,
            "slug": self.page.slug,
            "effective_date": "2026-11-01",
            "body": self.rich_text_json(),
            "comments-TOTAL_FORMS": "0", "comments-INITIAL_FORMS": "0",
            "comments-MIN_NUM_FORMS": "0", "comments-MAX_NUM_FORMS": "1000",
        }
        if action:
            data[action] = "1"
        return self.client.post(reverse("wagtailadmin_pages:edit", args=[self.page.pk]), data)

    def rich_text_json(self):
        from wagtail.admin.rich_text.converters.contentstate import ContentstateConverter

        return ContentstateConverter(features=["h2", "bold", "link"]).from_database_format(
            "<h2>Who we are</h2><p>Write to {{CONTACT_EMAIL}}.</p>"
        )

    def test_publish_blocked_while_a_used_value_is_blank_but_draft_saves(self):
        response = self.post_edit("action-publish")
        self.assertRedirects(response, reverse("wagtailadmin_pages:edit", args=[self.page.pk]),
                             fetch_redirect_response=False)
        page = LegalPage.objects.get(pk=self.page.pk)
        self.assertFalse(page.live)
        self.assertIn("{{CONTACT_EMAIL}}", page.get_latest_revision_as_object().body)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Contact email" in m for m in messages), messages)

    def test_draft_save_is_never_blocked(self):
        response = self.post_edit(None)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            LegalPage.objects.get(pk=self.page.pk).get_latest_revision_as_object().effective_date,
            datetime.date(2026, 11, 1),
        )

    def test_publish_allowed_once_filled(self):
        fill_details()
        self.post_edit("action-publish")
        self.assertTrue(LegalPage.objects.get(pk=self.page.pk).live)

    def test_publish_problem_names_every_missing_field(self):
        problem = LegalPage.objects.get(slug="copyright-policy").publish_problem()
        for name in ("DMCA agent name", "DMCA agent address", "DMCA agent phone",
                     "DMCA agent email", "Contact email"):
            self.assertIn(name, problem)
        fill_details()
        self.assertEqual(LegalPage.objects.get(slug="copyright-policy").publish_problem(), "")


class LegalPageRenderTests(LegalSiteTestCase):
    def setUp(self):
        super().setUp()
        self.run_command("--effective", "2026-11-01")
        fill_details(operator_name="John <b>Doe</b>")
        self.page = self.publish("privacy-policy")

    def test_renders_title_date_toc_and_filled_tokens(self):
        html = self.client.get(self.page.url).content.decode()
        self.assertIn("<h1>Privacy Policy</h1>", html)
        self.assertIn("Effective November 1, 2026", html)
        self.assertIn('<a href="#1-who-we-are">1. Who we are</a>', html)
        self.assertRegex(html, r'<h2[^>]* id="1-who-we-are">1. Who we are</h2>')
        self.assertIn("John &lt;b&gt;Doe&lt;/b&gt;", html)
        self.assertIn('href="mailto:legal@example.com"', html)
        self.assertIn("css/legal.css", html)

    def test_live_page_never_shows_a_raw_token(self):
        details = LegalDetails.load()
        details.contact_email = ""
        details.save()
        with self.assertLogs("home.legal", level="WARNING"):
            html = self.client.get(self.page.url).content.decode()
        self.assertNotIn("{{", html)


# --- Footer --------------------------------------------------------------------------


class FooterTests(LegalSiteTestCase):
    def footer(self):
        html = self.client.get(self.homepage.url).content.decode()
        return html[html.index('<footer class="site-footer">'):]

    def test_no_legal_links_or_heading_until_pages_are_live(self):
        self.run_command()
        footer = self.footer()
        self.assertNotIn("Legal &amp; Policies", footer)
        self.assertNotIn("/privacy-policy/", footer)
        self.assertNotIn("Accessibility</a>", footer)

    def test_only_live_legal_pages_are_linked(self):
        self.run_command()
        fill_details()
        self.publish("privacy-policy")
        self.publish("accessibility")
        footer = self.footer()
        self.assertIn("Legal &amp; Policies", footer)
        self.assertIn('<a href="/privacy-policy/">Privacy Policy</a>', footer)
        self.assertNotIn("/terms-of-use/", footer)
        self.assertIn('· <a href="/accessibility/">Accessibility</a>', footer)
        # The newsletter notice links to the live Privacy Policy too.
        self.assertIn('Unsubscribe anytime. See our <a href="/privacy-policy/">Privacy Policy</a>.', footer)

    def test_group_order_and_labels(self):
        self.run_command()
        fill_details()
        self.publish("terms-of-use")
        footer = self.footer()
        headings = re.findall(r"<h3>(.*?)</h3>", footer)
        self.assertEqual(headings, ["Explore", "Learn &amp; About", "Legal &amp; Policies", "Stay Inspired"])
        self.assertIn("Receive sacred site highlights, pilgrimage inspiration, and Catholic resources.", footer)
        self.assertIn(">Sign Up</button>", footer)
        self.assertIn("is not affiliated with or endorsed by the Holy See", footer)

    def test_support_link_label(self):
        support_page = SupportPage(title="Support Sites of Grace")
        self.homepage.add_child(instance=support_page)
        footer = self.footer()
        self.assertIn(">Support Sites of Grace</a>", footer)
        self.assertNotIn("♡", footer)


# --- Sign-up ---------------------------------------------------------------------------


@override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
class SignupNoticeTests(LegalSiteTestCase):
    def test_notice_renders_above_the_button(self):
        html = self.client.get(reverse("account_signup")).content.decode()
        notice = html.index("By creating an account, you agree to the")
        self.assertLess(notice, html.index(">Sign Up</button>"))
        self.assertIn('name="age_confirmed"', html)

    def test_signup_stores_terms_acceptance_and_version(self):
        self.run_command("--effective", "2026-11-01")
        fill_details()
        self.publish("terms-of-use")
        self.client.post(reverse("account_signup"), {
            "email": "jane.doe@example.com", "password1": "Pilgrim-Test-2026!",
            "password2": "Pilgrim-Test-2026!", "age_confirmed": "on",
        })
        profile = get_user_model().objects.get(email="jane.doe@example.com").pilgrim
        self.assertIsNotNone(profile.terms_accepted_at)
        self.assertEqual(profile.terms_version, "2026-11-01")

    def test_terms_version_blank_without_a_live_terms_page(self):
        self.client.post(reverse("account_signup"), {
            "email": "jane.doe@example.com", "password1": "Pilgrim-Test-2026!",
            "password2": "Pilgrim-Test-2026!", "age_confirmed": "on",
        })
        profile = get_user_model().objects.get(email="jane.doe@example.com").pilgrim
        self.assertIsNotNone(profile.terms_accepted_at)
        self.assertEqual(profile.terms_version, "")


# --- Support: amounts and Stripe text ---------------------------------------------------


STRIPE_ON = override_settings(
    STRIPE_SECRET_KEY="sk_test_FAKEKEYabcd1234", STRIPE_SUPPORT_PRODUCT_ID="prod_TESTSUPPORT",
    SUPPORT_ENABLED=True,
)


class SupportLegalTests(LegalSiteTestCase):
    def setUp(self):
        super().setUp()
        self.page = SupportPage(title="Support Sites of Grace")
        self.homepage.add_child(instance=self.page)

    def created_params(self, **post):
        session = stripe.checkout.Session.construct_from(
            {"id": "cs_test_a1B2c3D4", "url": "https://checkout.stripe.com/c/pay/cs_test_a1B2c3D4"},
            "sk_test_FAKEKEYabcd1234",
        )
        with STRIPE_ON, mock.patch("stripe.checkout.Session.create", return_value=session) as create:
            self.client.post(self.page.url, post)
        return create.call_args.kwargs

    def test_monthly_session_carries_the_authorization_text_with_the_amount(self):
        params = self.created_params(frequency="monthly", amount="other", custom_amount="12.50")
        message = params["custom_text"]["submit"]["message"]
        # The not-tax-deductible sentence comes first, then the authorization.
        self.assertTrue(message.startswith(support.CHECKOUT_SUBMIT_MESSAGE + " By confirming"), message)
        self.assertLessEqual(len(message), support.STRIPE_SUBMIT_MESSAGE_MAX)
        self.assertIn("authorize Sites of Grace to charge $12.50 every month", message)
        self.assertNotIn("{amount}", message)
        self.assertNotIn("**", message)

    def test_one_time_session_is_unchanged(self):
        params = self.created_params(frequency="once", amount="10")
        self.assertEqual(params["custom_text"]["submit"]["message"], support.CHECKOUT_SUBMIT_MESSAGE)

    def test_server_rejects_amounts_outside_one_to_a_thousand_whatever_the_page_says(self):
        SupportPage.objects.filter(pk=self.page.pk).update(min_amount=0, max_amount=5000)
        page = SupportPage.objects.get(pk=self.page.pk)
        with self.assertRaises(support.AmountError):
            support.amount_to_cents(page, "other", "1001")
        with self.assertRaises(support.AmountError):
            support.amount_to_cents(page, "other", "0.50")
        self.assertEqual(support.amount_to_cents(page, "other", "1000"), 100000)
        with STRIPE_ON, mock.patch("stripe.checkout.Session.create") as create:
            html = self.client.post(page.url, {"frequency": "once", "amount": "other",
                                               "custom_amount": "2500"}).content.decode()
        create.assert_not_called()
        self.assertIn("Please choose an amount from $1 to $1,000.", html)

    def test_page_validators(self):
        for changes, field in (({"max_amount": 1001}, "max_amount"),
                               ({"min_amount": 0}, "min_amount"),
                               ({"min_amount": 50, "max_amount": 50}, "max_amount")):
            page = SupportPage.objects.get(pk=self.page.pk)
            for name, value in changes.items():
                setattr(page, name, value)
            with self.subTest(changes), self.assertRaises(ValidationError) as ctx:
                page.full_clean()
            self.assertIn(field, ctx.exception.message_dict)

    def test_intro_and_monthly_notices_render(self):
        self.page.manage_url = "https://billing.stripe.com/p/login/test_fake"
        self.page.save_revision().publish()
        with STRIPE_ON:
            html = self.client.get(self.page.url).content.decode()
        intro = html.index("Support is optional.")
        self.assertLess(intro, html.index("support-submit"))
        self.assertIn("data-support-monthly hidden", html)
        self.assertIn('<span data-notice-amount>$10</span>', html)
        self.assertIn('<a href="https://billing.stripe.com/p/login/test_fake" rel="noopener">Manage monthly support</a>', html)
        self.assertNotIn(self.page.disclaimer, html)


# --- Policy fixes that shipped with the legal pages ------------------------------------


class PolicyFixTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_newsletter_is_rate_limited(self):
        from core.models import NewsletterSignup
        from core.views import NEWSLETTER_LIMIT

        for i in range(NEWSLETTER_LIMIT):
            self.client.post(reverse("newsletter_signup"), {"email": f"john.doe{i}@example.com", "next": "/"})
        response = self.client.post(reverse("newsletter_signup"), {"email": "jane.doe@example.com", "next": "/"})
        self.assertIn("newsletter_error=rate", response.url)
        self.assertEqual(NewsletterSignup.objects.count(), NEWSLETTER_LIMIT)

    def test_waitlist_is_rate_limited(self):
        from store.views import WAITLIST_LIMIT

        for i in range(WAITLIST_LIMIT):
            self.client.post(reverse("waitlist_signup"), {"email": f"john.doe{i}@example.com", "product_id": "1", "next": "/"})
        response = self.client.post(reverse("waitlist_signup"), {"email": "jane.doe@example.com", "product_id": "1", "next": "/"})
        self.assertIn("waitlist_error=rate", response.url)

    def test_no_unpkg_and_no_admin_calls_out(self):
        for template in ("home/map_page.html", "catalog/pilgrimage_trail_page.html", "pilgrims/profile_detail.html"):
            from django.template.loader import get_template

            source = get_template(template).template.source
            with self.subTest(template):
                self.assertNotIn("unpkg.com", source)
                self.assertIn("vendor/leaflet-1.9.4/leaflet.js", source)
        self.assertIsNone(settings.WAGTAIL_GRAVATAR_PROVIDER_URL)
        self.assertFalse(settings.WAGTAIL_ENABLE_UPDATE_CHECK)

    def test_vendored_source_maps_exist(self):
        # The production build's CompressedManifestStaticFilesStorage fails
        # collectstatic if a sourceMappingURL points at a missing file.
        vendor = settings.BASE_DIR / "sitesofgrace" / "static" / "vendor"
        for path in vendor.rglob("*.js"):
            for name in re.findall(r"sourceMappingURL=(\S+)", path.read_text(encoding="utf-8")):
                with self.subTest(str(path)):
                    self.assertTrue((path.parent / name).exists(), f"{path.name} -> {name}")

    def test_gunicorn_access_log_has_no_query_strings(self):
        dockerfile = (settings.BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
        cmd = dockerfile[dockerfile.index('CMD ["gunicorn"'):]
        self.assertIn("--access-logformat", cmd)
        self.assertIn("%(U)s", cmd)
        self.assertNotIn("%(r)s", cmd)
        self.assertNotIn("%(q)s", cmd)
        self.assertNotIn("%(f)s", cmd)
