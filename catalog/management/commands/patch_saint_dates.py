"""Patch feast_day and canonized on EXISTING saint pages, and nothing else.

Why this exists: import_catalog overwrites every field it reads, so putting an
existing saint in the Saints tab with a blank `significance` or `body_draft`
erases the narrative already on that page. This command reads the
`Existing_Date_Updates` tab of the same workbook and writes only the two date
fields, leaving all narrative untouched.

    python manage.py patch_saint_dates SitesOfGrace_Saints_EXPANSION_2026-09.xlsx
    python manage.py patch_saint_dates <workbook> --dry-run
"""
import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SaintPage

SHEET = "Existing_Date_Updates"


def s(value):
    return "" if value is None else str(value).strip()


class Command(BaseCommand):
    help = "Patch feast_day / canonized on existing SaintPages from the expansion workbook."

    def add_arguments(self, parser):
        parser.add_argument("workbook", help="Path to the expansion .xlsx.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change and roll back. Nothing is saved.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Also save a published revision, so the change is live immediately. "
            "Without this the field is written to the page record only.",
        )

    def handle(self, *args, **options):
        try:
            wb = openpyxl.load_workbook(options["workbook"], data_only=True)
        except FileNotFoundError:
            raise CommandError(f"Workbook not found: {options['workbook']}")
        if SHEET not in wb.sheetnames:
            raise CommandError(f"Workbook has no '{SHEET}' tab.")

        rows = wb[SHEET].iter_rows(values_only=True)
        header = [s(c) for c in next(rows)]
        records = [dict(zip(header, r)) for r in rows if any(c is not None for c in r)]

        changed, skipped, missing = [], [], []
        with transaction.atomic():
            for rec in records:
                slug = s(rec.get("slug"))
                if not slug:
                    continue
                saint = SaintPage.objects.filter(slug=slug).first()
                if saint is None:
                    missing.append(slug)
                    continue

                new_feast = s(rec.get("feast_day_new"))
                new_canon = s(rec.get("canonized_new"))
                before = (saint.feast_day, saint.canonized)

                if new_feast and new_feast != saint.feast_day:
                    saint.feast_day = new_feast
                if new_canon and new_canon not in (saint.canonized or ""):
                    saint.canonized = (
                        f"{saint.canonized} ({new_canon})".strip()
                        if saint.canonized
                        else new_canon
                    )

                if (saint.feast_day, saint.canonized) == before:
                    skipped.append(slug)
                    continue

                saint.save(update_fields=["feast_day", "canonized"])
                if options["publish"]:
                    revision = saint.save_revision()
                    revision.publish()
                changed.append(
                    f"{saint.title}: feast {before[0]!r} -> {saint.feast_day!r}, "
                    f"canonized {before[1]!r} -> {saint.canonized!r}"
                )

            if options["dry_run"]:
                transaction.set_rollback(True)

        for line in changed:
            self.stdout.write("  " + line)
        if missing:
            self.stdout.write(self.style.WARNING(f"  no page for slug: {', '.join(missing)}"))
        verb = "would change" if options["dry_run"] else "changed"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {len(changed)}, already correct {len(skipped)}, "
                f"not found {len(missing)}, rows read {len(records)}"
            )
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run -- rolled back, nothing saved"))
