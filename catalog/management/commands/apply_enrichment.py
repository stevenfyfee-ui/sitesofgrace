"""Apply Wikidata enrichment to existing SaintPages.

Reads tools/saints_data/enrichment.csv (or a CSV passed as the first
argument) and writes ONLY five fields: wikidata_id, religious_order,
burial_place, portrait_url, portrait_credit. born, died and feast_day are
also filled, but only where currently blank. patronage is never touched --
ours has better coverage than Wikidata's.

Rules:
  - Rows whose confidence is AMBIGUOUS are skipped entirely. Wikidata itself
    could not tell which of several people the row refers to; writing any of
    its fields would risk attaching the wrong person's data to a real saint.
  - An existing non-empty field always wins. This only fills blanks.
  - portrait_url is normalized on write (https, ?width=500) regardless of
    what the CSV holds -- see normalize_image_url below.
  - portrait_credit is filled only alongside portrait_url, from the CSV's
    image_credit column (blank for public-domain images, which need none;
    set to a compliant attribution string for CC BY / CC BY-SA images by
    enrich_licenses.py).

    python manage.py apply_enrichment --dry-run
    python manage.py apply_enrichment
    python manage.py apply_enrichment --publish
    python manage.py apply_enrichment path/to/other.csv --dry-run
"""
import csv
import os
import re
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SaintPage

DEFAULT_CSV_PATH = os.path.join(settings.BASE_DIR, "tools", "saints_data", "enrichment.csv")


def normalize_image_url(url: str) -> str:
    """https, and a display width -- mirrors wikidata_saints.py's helper of
    the same name. Duplicated rather than imported so the database is
    correct regardless of what the CSV holds, even from an older harvest or
    a hand-edited file that never went through wikidata_saints.py at all."""
    if not url:
        return url
    url = re.sub(r"^http://", "https://", url)
    if "width=" not in url:
        url += ("&" if "?" in url else "?") + "width=500"
    return url

# Filled straight from the matching CSV column whenever the model field is
# currently blank. born/died/feast_day are already display-ready strings by
# the time they reach this CSV (wikidata_saints.py resolves the year out of
# Wikidata's ISO timestamps and the feast label out of its entity URI) --
# this command just copies them across, it doesn't reformat anything.
DIRECT_FIELDS = [
    ("wikidata_id", "qid"),
    ("religious_order", "order"),
    ("burial_place", "burial"),
    ("born", "born"),
    ("died", "died"),
    ("feast_day", "feast_day"),
]


class Command(BaseCommand):
    help = "Fill blank fields on existing SaintPages from tools/saints_data/enrichment.csv."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default=DEFAULT_CSV_PATH,
                            help="Path to the enrichment CSV (default: "
                                 "tools/saints_data/enrichment.csv).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change and roll back.")
        parser.add_argument("--publish", action="store_true",
                            help="Also publish a revision so the change is live "
                                 "immediately, rather than sitting on the page record.")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        if not os.path.exists(csv_path):
            raise CommandError(f"Not found: {csv_path}")

        with open(csv_path, encoding="utf8") as fh:
            rows = list(csv.DictReader(fh))

        applied, skipped_ambiguous, missing = [], [], []
        field_counts = Counter()
        credits_added = 0

        with transaction.atomic():
            for row in rows:
                slug = (row.get("slug") or "").strip()
                if not slug:
                    continue
                if row.get("confidence", "").startswith("AMBIGUOUS"):
                    skipped_ambiguous.append(slug)
                    continue

                saint = SaintPage.objects.filter(slug=slug).first()
                if saint is None:
                    missing.append(slug)
                    continue

                update_fields = []

                for model_field, csv_field in DIRECT_FIELDS:
                    value = (row.get(csv_field) or "").strip()
                    if value and not getattr(saint, model_field):
                        setattr(saint, model_field, value)
                        update_fields.append(model_field)
                        field_counts[model_field] += 1

                image_url = normalize_image_url((row.get("image_url") or "").strip())
                if image_url and not saint.portrait_url:
                    saint.portrait_url = image_url
                    update_fields.append("portrait_url")
                    field_counts["portrait_url"] += 1
                    credit = (row.get("image_credit") or "").strip()
                    if credit and not saint.portrait_credit:
                        saint.portrait_credit = credit
                        update_fields.append("portrait_credit")
                        field_counts["portrait_credit"] += 1
                        credits_added += 1

                if not update_fields:
                    continue

                saint.save(update_fields=update_fields)
                if options["publish"]:
                    revision = saint.save_revision()
                    revision.publish()
                applied.append(f"{saint.title}: {', '.join(update_fields)}")

            if options["dry_run"]:
                transaction.set_rollback(True)

        verb = "would apply" if options["dry_run"] else "applied"
        for line in applied:
            self.stdout.write("  " + line)
        if missing:
            self.stdout.write(self.style.WARNING(f"  no page for slug: {', '.join(missing)}"))

        self.stdout.write(self.style.SUCCESS(
            f"{verb} changes to {len(applied)} saints; "
            f"skipped {len(skipped_ambiguous)} AMBIGUOUS rows; "
            f"{len(missing)} slugs not found; rows read {len(rows)}"
        ))
        self.stdout.write("fields filled, by type:")
        for field, count in field_counts.most_common():
            self.stdout.write(f"  {field:18} {count}")
        self.stdout.write(f"portraits given a credit line: {credits_added}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run -- rolled back, nothing saved"))
