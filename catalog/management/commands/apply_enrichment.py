"""Apply Wikidata enrichment to existing SaintPages.

Reads tools/saints_data/enrichment.csv and writes ONLY five fields:
wikidata_id, religious_order, burial_place, portrait_url, portrait_credit.
born, died and feast_day are also filled, but only where currently blank.
patronage is never touched -- ours has better coverage than Wikidata's.

Rules:
  - Rows whose confidence is AMBIGUOUS are skipped entirely. Wikidata itself
    could not tell which of several people the row refers to; writing any of
    its fields would risk attaching the wrong person's data to a real saint.
  - An existing non-empty field always wins. This only fills blanks.
  - portrait_credit is filled only alongside portrait_url, from the CSV's
    image_credit column (blank for public-domain images, which need none;
    set to a compliant attribution string for CC BY / CC BY-SA images by
    enrich_licenses.py).

    python manage.py apply_enrichment --dry-run
    python manage.py apply_enrichment
    python manage.py apply_enrichment --publish
"""
import csv
import os
import re
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SaintPage

CSV_PATH = os.path.join(settings.BASE_DIR, "tools", "saints_data", "enrichment.csv")

# wikidata_id, religious_order, burial_place, portrait_url: filled straight
# from the matching CSV column whenever the model field is currently blank.
DIRECT_FIELDS = [
    ("wikidata_id", "qid"),
    ("religious_order", "order"),
    ("burial_place", "burial"),
]


def year_from_iso(value: str) -> str:
    """'1181-01-01T00:00:00Z' -> '1181'; '-0017-01-01T...' -> '17 BC'."""
    m = re.match(r"^(-?\d+)-\d{2}-\d{2}", value or "")
    if not m:
        return ""
    year = int(m.group(1))
    return f"{abs(year)} BC" if year < 0 else str(year)


class Command(BaseCommand):
    help = "Fill blank fields on existing SaintPages from tools/saints_data/enrichment.csv."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change and roll back.")
        parser.add_argument("--publish", action="store_true",
                            help="Also publish a revision so the change is live "
                                 "immediately, rather than sitting on the page record.")

    def handle(self, *args, **options):
        if not os.path.exists(CSV_PATH):
            raise CommandError(f"Not found: {CSV_PATH}")

        with open(CSV_PATH, encoding="utf8") as fh:
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

                image_url = (row.get("image_url") or "").strip()
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

                born = year_from_iso(row.get("birth_raw", ""))
                if born and not saint.born:
                    saint.born = born
                    update_fields.append("born")
                    field_counts["born"] += 1

                died = year_from_iso(row.get("death_raw", ""))
                if died and not saint.died:
                    saint.died = died
                    update_fields.append("died")
                    field_counts["died"] += 1

                feast = (row.get("feast_raw") or "").strip()
                if feast and not saint.feast_day:
                    saint.feast_day = feast
                    update_fields.append("feast_day")
                    field_counts["feast_day"] += 1

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
