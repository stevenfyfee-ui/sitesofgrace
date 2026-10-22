"""Write a CSV worksheet of every Eucharistic page for hand classification.

    python manage.py eucharistic_kind_worksheet --out eucharistic_kind.csv

Read-only: it lists pages and classifies nothing. Columns: id, title, url,
current eucharistic_kind (usually blank), and the first 200 characters of
the story as plain text. Fill in eucharistic_kind, then load it with
import_site_details.
"""
import csv

from django.core.management.base import BaseCommand
from django.utils.html import strip_tags
from django.utils.text import normalize_newlines

from catalog.models import SacredSitePage

EUCHARISTIC_CATEGORY = "Eucharistic Miracle"
EXCERPT_CHARS = 200


def plain_excerpt(html, limit=EXCERPT_CHARS):
    text = " ".join(normalize_newlines(strip_tags(html or "")).split())
    return text[:limit]


class Command(BaseCommand):
    help = "CSV of every Eucharistic page (id, title, url, story excerpt) for classification."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Path of the CSV to write.")

    def handle(self, *args, **options):
        pages = SacredSitePage.objects.filter(category=EUCHARISTIC_CATEGORY).order_by("title")
        count = 0
        with open(options["out"], "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "title", "url", "live", "eucharistic_kind", "story_first_200"])
            for page in pages:
                writer.writerow([
                    page.pk, page.title, page.full_url or page.url_path, page.live,
                    page.eucharistic_kind or "", plain_excerpt(page.the_story),
                ])
                count += 1
        self.stdout.write(f"wrote {count} Eucharistic pages to {options['out']}")
