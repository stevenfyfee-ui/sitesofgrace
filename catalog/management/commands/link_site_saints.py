"""Wire sacred sites to their saints from the expansion workbook.

Reads the `Site_Saint_Links` tab and sets two things per site:

  associated_saint  the saint the site principally belongs to (a ForeignKey)
  related_saints    everyone else connected to it (the new many-to-many)

It touches ONLY those two fields. Unlike import_catalog, which overwrites
every column it reads, this cannot erase a site's narrative.

An existing associated_saint is never overwritten. If the workbook proposes a
different principal saint for a site an editor has already filled in, the
editor wins and the proposal is demoted into related_saints instead.

    python manage.py link_site_saints <workbook> --dry-run
    python manage.py link_site_saints <workbook>
    python manage.py link_site_saints <workbook> --publish
"""
import re
import unicodedata

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SacredSitePage, SaintPage

SHEET = "Site_Saint_Links"
LIGATURES = {"æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "ł": "l"}
HONORIFIC = re.compile(r"\b(sts?|saints?|blessed|bl|pope)\b", re.I)


def s(value):
    return "" if value is None else str(value).strip()


def fold(name):
    """Normalise a saint name for matching.

    The Site_Saint_Links tab was written with plain-ASCII names, while the
    imported pages carry restored diacritics ("St. Catherine Labouré"), so
    both sides have to be folded before they will compare equal.
    """
    text = s(name)
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9 ]", " ", text)
    text = HONORIFIC.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


class Command(BaseCommand):
    help = "Set associated_saint and related_saints on sacred sites from the workbook."

    def add_arguments(self, parser):
        parser.add_argument("workbook", help="Path to the expansion .xlsx.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change and roll back.")
        parser.add_argument("--publish", action="store_true",
                            help="Also publish a revision so the change is live "
                                 "immediately, rather than sitting on the page record.")

    def handle(self, *args, **options):
        try:
            wb = openpyxl.load_workbook(options["workbook"], data_only=True)
        except FileNotFoundError:
            raise CommandError(f"Workbook not found: {options['workbook']}")
        if SHEET not in wb.sheetnames:
            raise CommandError(f"Workbook has no '{SHEET}' tab.")

        if not hasattr(SacredSitePage, "related_saints"):
            raise CommandError(
                "SacredSitePage has no related_saints field yet. Run "
                "`manage.py makemigrations catalog` and `manage.py migrate` first."
            )

        rows = wb[SHEET].iter_rows(values_only=True)
        header = [s(c) for c in next(rows)]
        records = [dict(zip(header, r)) for r in rows if any(c is not None for c in r)]

        # One lookup for every saint page, folded. Ordered by pk so that a
        # duplicate pair (the database has "St. Martha" and "Sts. Martha")
        # always resolves to the same page instead of whichever the database
        # happened to return first.
        saints, ambiguous = {}, {}
        for saint in SaintPage.objects.order_by("pk"):
            k = fold(saint.title)
            if k in saints:
                ambiguous.setdefault(k, [saints[k].title]).append(saint.title)
                continue
            saints[k] = saint
        for k, titles in ambiguous.items():
            self.stdout.write(self.style.WARNING(
                f"  duplicate saint pages collapse to '{k}': {', '.join(titles)} "
                f"-- linking to '{saints[k].title}'. Merge them when you get a chance."
            ))

        filled, related_set, kept, missing_sites, unresolved = [], [], 0, [], set()

        with transaction.atomic():
            for rec in records:
                slug = s(rec.get("slug"))
                if not slug:
                    continue
                site = SacredSitePage.objects.filter(slug=slug).first()
                if site is None:
                    missing_sites.append(slug)
                    continue

                proposed = s(rec.get("associated_saint_proposed"))
                related_names = [
                    n.strip() for n in s(rec.get("related_saints_proposed")).split(";")
                    if n.strip()
                ]

                def resolve(name):
                    hit = saints.get(fold(name))
                    if hit is None:
                        unresolved.add(name)
                    return hit

                changed_fk = False
                extra = []

                if proposed:
                    saint = resolve(proposed)
                    if saint is not None:
                        if site.associated_saint_id is None:
                            site.associated_saint = saint
                            changed_fk = True
                            filled.append(f"{site.title} -> {saint.title}")
                        elif site.associated_saint_id != saint.pk:
                            # an editor already chose; respect it, demote ours
                            extra.append(saint)
                            kept += 1

                targets = []
                for name in related_names:
                    saint = resolve(name)
                    if saint is not None:
                        targets.append(saint)
                targets.extend(extra)

                # never list the principal saint in related_saints as well
                principal = site.associated_saint_id
                targets = [t for t in targets if t.pk != principal]
                # de-duplicate, keep order
                seen, ordered = set(), []
                for t in targets:
                    if t.pk not in seen:
                        seen.add(t.pk)
                        ordered.append(t)

                if changed_fk:
                    site.save(update_fields=["associated_saint"])

                if ordered:
                    current = set(site.related_saints.values_list("pk", flat=True))
                    if current != {t.pk for t in ordered}:
                        site.related_saints.set(ordered)
                        related_set.append(
                            f"{site.title} + {', '.join(t.title for t in ordered)}"
                        )

                if (changed_fk or ordered) and options["publish"]:
                    site.save_revision().publish()

            if options["dry_run"]:
                transaction.set_rollback(True)

        verb = "would fill" if options["dry_run"] else "filled"
        for line in filled:
            self.stdout.write("  " + line)
        for line in related_set:
            self.stdout.write("  " + line)
        if missing_sites:
            self.stdout.write(self.style.WARNING(
                f"  no site page for slug: {', '.join(missing_sites)}"))
        if unresolved:
            self.stdout.write(self.style.WARNING(
                "  saint not found (skipped, nothing written for these): "
                + ", ".join(sorted(unresolved))))

        self.stdout.write(self.style.SUCCESS(
            f"{verb} {len(filled)} principal saints; set related_saints on "
            f"{len(related_set)} sites; left {kept} editor-chosen links alone; "
            f"rows read {len(records)}"
        ))
        blank = SacredSitePage.objects.filter(associated_saint__isnull=True).count()
        self.stdout.write(f"sites still without a principal saint: {blank}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run -- rolled back, nothing saved"))
