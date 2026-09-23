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

--dry-run does one read-only pass -- no saves, no transaction, nothing to
roll back. It exists to answer "how many rows would this touch", and does
that with a single query plus in-memory comparisons, not by doing the
real write and undoing it.

A real run writes with a single bulk_update() rather than one Page.save()
per row: none of these fields are in SaintPage's search_fields (only
title and structural fields are), no signal handler outside Wagtail's own
search indexing is registered for Page saves in this codebase, and this
command never creates a revision unless --publish is passed -- so the
per-row Page.save() machinery (full_clean, the slug-changed check, a
synchronous search reindex) was pure overhead here, not a used feature.
--publish still runs the normal per-page save_revision()+publish() path
afterward, since creating revisions has no bulk equivalent in Wagtail.

    python manage.py apply_enrichment --dry-run
    python manage.py apply_enrichment
    python manage.py apply_enrichment --publish
    python manage.py apply_enrichment path/to/other.csv --dry-run
"""
import csv
import os
import re
import time
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SaintPage

DEFAULT_CSV_PATH = os.path.join(settings.BASE_DIR, "tools", "saints_data", "enrichment.csv")
PROGRESS_EVERY = 50


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
                            help="Report what would change. Read-only -- no transaction, nothing to roll back.")
        parser.add_argument("--publish", action="store_true",
                            help="Also publish a revision so the change is live "
                                 "immediately, rather than sitting on the page record.")

    def progress(self, i, total, applied_so_far):
        if i % PROGRESS_EVERY == 0 or i == total:
            self.stdout.write(f"  ...scanned {i}/{total}, {applied_so_far} would be enriched so far")
            self.stdout.flush()

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        dry_run = options["dry_run"]
        if not os.path.exists(csv_path):
            raise CommandError(f"Not found: {csv_path}")

        start = time.monotonic()
        with open(csv_path, encoding="utf8") as fh:
            rows = list(csv.DictReader(fh))
        total = len(rows)

        slugs = {(row.get("slug") or "").strip() for row in rows if (row.get("slug") or "").strip()}
        saints_by_slug = {s.slug: s for s in SaintPage.objects.filter(slug__in=slugs)}
        self.stdout.write(f"loaded {total} rows, matched {len(saints_by_slug)} existing saints")
        self.stdout.flush()

        applied, skipped_ambiguous, missing = [], [], []
        field_counts = Counter()
        credits_added = 0
        to_write = []
        touched_fields = set()

        for i, row in enumerate(rows, start=1):
            slug = (row.get("slug") or "").strip()
            if not slug:
                self.progress(i, total, len(applied))
                continue
            if row.get("confidence", "").startswith("AMBIGUOUS"):
                skipped_ambiguous.append(slug)
                self.progress(i, total, len(applied))
                continue

            saint = saints_by_slug.get(slug)
            if saint is None:
                missing.append(slug)
                self.progress(i, total, len(applied))
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

            if update_fields:
                applied.append(f"{saint.title}: {', '.join(update_fields)}")
                touched_fields.update(update_fields)
                if not dry_run:
                    to_write.append(saint)

            self.progress(i, total, len(applied))

        scan_elapsed = time.monotonic() - start
        self.stdout.write(f"scan complete in {scan_elapsed:.2f}s")
        self.stdout.flush()

        if not dry_run and to_write:
            write_start = time.monotonic()
            with transaction.atomic():
                SaintPage.objects.bulk_update(to_write, sorted(touched_fields), batch_size=200)
            self.stdout.write(
                f"wrote {len(to_write)} saints in one bulk update "
                f"({', '.join(sorted(touched_fields))}) in {time.monotonic() - write_start:.2f}s"
            )
            self.stdout.flush()

            if options["publish"]:
                publish_start = time.monotonic()
                self.stdout.write(f"publishing a revision for {len(to_write)} saints...")
                self.stdout.flush()
                for n, saint in enumerate(to_write, start=1):
                    revision = saint.save_revision()
                    revision.publish()
                    if n % PROGRESS_EVERY == 0 or n == len(to_write):
                        self.stdout.write(f"  ...published {n}/{len(to_write)}")
                        self.stdout.flush()
                self.stdout.write(f"publish complete in {time.monotonic() - publish_start:.2f}s")
                self.stdout.flush()

        verb = "would apply" if dry_run else "applied"
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
        if dry_run:
            self.stdout.write(self.style.WARNING("dry run -- read-only, nothing written"))
        self.stdout.write(f"total time: {time.monotonic() - start:.2f}s")

        # Structured result for callers that compose this command (e.g.
        # sync_catalog) -- not returned from handle(), since Django's
        # execute() would try to treat a non-string return value as stdout
        # output. Read it off the Command instance after call_command(cmd, ...).
        self.result = {
            "applied": len(applied),
            "skipped_ambiguous": len(skipped_ambiguous),
            "missing": len(missing),
            "field_counts": dict(field_counts),
            "credits_added": credits_added,
        }
