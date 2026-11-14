""""A Note for Grown-Ups": the approved wording word for word, the two placeholder fields and the
publish guard, the tree command, the footer link and the Privacy Policy link inside the page."""
import datetime
import html as html_lib
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.urls import reverse
from wagtail.test.utils.form_data import inline_formset, nested_form_data

from future_saints.grownups import GrownUpsNotePage
from home.models import LegalPage

from .base import FS_OFF, FS_ON, FS_STAFF, FutureSaintsTestCase
from .test_world_map import BANNED as WORLD_BANNED

APPROVED = Path(settings.BASE_DIR) / "docs" / "future-saints" / "content" / "future-saints-note-for-grown-ups.md"
URL = "/future-saints/for-grown-ups/"
ADDRESS = "Sites of Grace\nPO Box 123 (sample)\nSpringfield, ST 00000"
# The approved sentences that use words banned elsewhere in Future Saints (each says what the
# section does NOT have). Removing exactly these must leave no banned word on the page.
APPROVED_NEGATIONS = (
    "No tracking, ads, or shopping",
    'show no ads, affiliate links, product recommendations, or "buy" buttons.',
    "Future Saints has no accounts, sign-ups, comments, chat, photo uploads, contests, or newsletters.",
)


def approved_lines():
    """The page part of the approved file (from "## A Note for Grown-Ups" to the effective date),
    as plain sentences: Markdown markup removed, placeholders kept."""
    text = APPROVED.read_text(encoding="utf-8")
    page = text.split("## A Note for Grown-Ups", 1)[1].split("\n---", 1)[0]
    lines = []
    for line in page.splitlines():
        line = re.sub(r"^#+\s*|^-\s+", "", line.strip())
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)          # [Privacy Policy](/privacy/)
        line = line.replace("**", "").strip("*").strip()
        if line:
            lines.append(line)
    return ["A Note for Grown-Ups"] + lines


def page_text(html):
    main = html.split('<main id="content">', 1)[1].split("</main>", 1)[0]
    text = re.sub(r"<br\s*/?>", " ", main)
    text = re.sub(r"</?(?:strong|em|a|span)\b[^>]*>", "", text)     # inline: no space added
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html_lib.unescape(text).split())


class GrownUpsTestCase(FutureSaintsTestCase):
    def setUp(self):
        super().setUp()
        self.note = GrownUpsNotePage.objects.get()          # made as a draft by create_future_saints_tree

    def fill_and_publish(self):
        self.note.mailing_address = ADDRESS
        self.note.effective_date = datetime.date(2026, 12, 1)
        self.note.save_revision().publish()
        self.note.refresh_from_db()

    def add_privacy_policy(self):
        privacy = LegalPage(title="Privacy Policy", slug="privacy-policy", effective_date=datetime.date(2026, 1, 1),
                            body="<p>Sample (sample).</p>")
        self.home.get_parent().add_child(instance=privacy)


class WordingTests(GrownUpsTestCase):
    def test_the_approved_text_word_for_word(self):
        self.fill_and_publish()
        with FS_ON:
            text = page_text(self.html(URL))
        for line in approved_lines():
            expected = line.replace("[MAILING ADDRESS]", " ".join(ADDRESS.split())) \
                           .replace("[EFFECTIVE DATE]", "December 1, 2026")
            self.assertIn(" ".join(expected.split()), text)
        self.assertNotIn("[MAILING ADDRESS]", text)
        self.assertNotIn("[EFFECTIVE DATE]", text)
        self.assertNotIn("Notes for Steven", text, "the reviewer notes are not part of the page")

    def test_banned_words_only_in_the_approved_negations(self):
        self.fill_and_publish()
        with FS_ON:
            text = page_text(self.html(URL))
        for sentence in APPROVED_NEGATIONS:
            self.assertIn(sentence, text)
            text = text.replace(sentence, " ")
        lower = text.lower()
        for word in set(WORLD_BANNED) | {"affiliate", "newsletter", "sign up", "signup", "donate"}:
            self.assertIsNone(re.search(rf"\b{re.escape(word)}\b", lower), word)


class PlaceholderTests(GrownUpsTestCase):
    def test_fields_fill_the_placeholders(self):
        self.fill_and_publish()
        with FS_ON:
            html = self.html(URL)
        self.assertIn("<strong data-fs-mailing-address>Sites of Grace<br>PO Box 123 (sample)<br>Springfield, ST 00000</strong>", html)
        self.assertIn("Effective <span data-fs-effective-date>December 1, 2026</span>.", html)
        self.assertIn('href="mailto:support@sitesofgrace.com"', html)

    def test_publish_problem(self):
        self.assertIn("Mailing address, Effective date", self.note.publish_problem())
        self.note.mailing_address = ADDRESS
        self.assertIn("Effective date", self.note.publish_problem())
        self.assertNotIn("Mailing address", self.note.publish_problem())
        self.note.effective_date = datetime.date(2026, 12, 1)
        self.assertEqual(self.note.publish_problem(), "")

    def post_edit(self, action, **fields):
        admin = type(self.staff).objects.create_superuser("fs-admin", "admin@example.com", "x")
        self.client.force_login(admin)
        data = nested_form_data({"title": self.note.title, "slug": self.note.slug, "comments": inline_formset([]),
                                 "mailing_address": "", "effective_date": "", **fields})
        data[action] = "1"
        return self.client.post(reverse("wagtailadmin_pages:edit", args=[self.note.pk]), data)

    def test_publishing_is_refused_while_a_field_is_blank_and_the_draft_is_kept(self):
        response = self.post_edit("action-publish", mailing_address=ADDRESS)
        self.assertEqual(response.status_code, 302)
        self.note.refresh_from_db()
        self.assertFalse(self.note.live, "not published without an effective date")
        self.assertEqual(self.note.get_latest_revision().as_object().mailing_address, ADDRESS, "the draft is kept")

    def test_publishing_works_once_both_are_filled(self):
        self.post_edit("action-publish", mailing_address=ADDRESS, effective_date="2026-12-01")
        self.note.refresh_from_db()
        self.assertTrue(self.note.live)
        self.assertEqual(self.note.effective_date, datetime.date(2026, 12, 1))

    def test_submitting_to_review_is_refused_while_a_field_is_blank(self):
        response = self.post_edit("action-submit", effective_date="2026-12-01")
        self.assertEqual(response.status_code, 200, "the form comes back with the error")
        self.assertContains(response, "Mailing address is required before this page goes to review or is published.")
        self.note.refresh_from_db()
        self.assertFalse(self.note.live)


class TreeTests(GrownUpsTestCase):
    def test_dry_run_then_draft(self):
        self.note.delete()
        out = StringIO()
        call_command("create_future_saints_tree", "--dry-run", stdout=out)
        self.assertIn("Would create (draft): GrownUpsNotePage  title 'A Note for Grown-Ups'  slug 'for-grown-ups'",
                      out.getvalue())
        self.assertFalse(GrownUpsNotePage.objects.exists(), "the dry run writes nothing")
        call_command("create_future_saints_tree", stdout=StringIO())
        note = GrownUpsNotePage.objects.get()
        self.assertFalse(note.live, "created as a draft")
        self.assertEqual(note.get_parent().pk, self.home.pk)
        self.assertEqual(note.url_path, self.home.url_path + "for-grown-ups/")
        self.assertFalse(GrownUpsNotePage.can_create_at(self.home), "one instance only")


class LinkTests(GrownUpsTestCase):
    def test_footer_links_the_note_not_the_privacy_policy(self):
        self.add_privacy_policy()
        with FS_STAFF:
            html = self.html("/future-saints/", self.staff)
        self.assertNotIn("A note for grown-ups</a>", html, "no link until the note is published")
        self.assertIn('the "A Note for Grown-Ups" page isn\'t published yet', html)
        self.fill_and_publish()
        with FS_ON:
            html = self.html("/future-saints/")
        self.assertIn(f'href="{URL}">A note for grown-ups</a>', html)
        self.assertNotIn('href="/privacy-policy/">A note for grown-ups</a>', html)
        self.assertNotIn("isn't published yet", html, "the staff note is staff only")

    def test_privacy_policy_link_inside_the_page(self):
        self.fill_and_publish()
        with FS_STAFF:
            html = self.html(URL, self.staff)
        self.assertIn("see our <strong>Privacy Policy</strong>.", html, "unlinked until the Privacy Policy is live")
        self.assertIn("the Privacy Policy isn't live yet", html)
        self.add_privacy_policy()
        with FS_ON:
            html = self.html(URL)
        self.assertIn('see our <strong><a href="/privacy-policy/">Privacy Policy</a></strong>.', html)

    def test_behind_the_switch(self):
        self.fill_and_publish()
        with FS_OFF:
            self.assertEqual(self.get(URL, self.staff).status_code, 404)
        with FS_STAFF:
            self.assertEqual(self.get(URL).status_code, 404)
            self.assertEqual(self.get(URL, self.staff).status_code, 200)
