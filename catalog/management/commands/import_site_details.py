"""Bulk-load the Phase 1 v2 site fields onto existing SacredSitePages.

    python manage.py import_site_details tools/*site_details*.json --dry-run
    python manage.py import_site_details tools/*site_details*.json
    python manage.py import_site_details tools/*site_details*.json --verify

Follows docs/v2/IMPORT-RULES.md. File shape:

    {"pages": [{"id": 123, "title": "Our Lady of Lourdes",
                "status": "Ready to import",
                "fields": {"address": "...", "visit_length": "one-day", ...}}]}

Only the fields in ALLOWED_FIELDS can be set. Blank / null / missing means
no change; a field that is already filled with something else is a conflict
and skips the whole page (Standing Rule 4: never overwrite a filled field).
"""
import glob
import json
from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import models, transaction
from wagtail.fields import RichTextField

from catalog.management.commands.import_saints import html_problem
from catalog.models import SacredSitePage

READY = "Ready to import"
EUCHARISTIC_CATEGORY = "Eucharistic Miracle"

# At a Glance, the "How to read this account" box, eucharistic_kind,
# guide_level, the prep fields, primary references and recognition_year.
ALLOWED_FIELDS = [
    "address", "time_needed", "visit_length", "admission", "reservation_required",
    "accessibility_summary", "accessibility_level",
    "worship_status", "worship_note", "worship_schedule_url",
    "account_tradition", "account_church_judgment", "account_findings", "account_teaching",
    "eucharistic_kind", "guide_level",
    "prep_prayer", "prep_readings", "primary_references",
    "recognition_year",
]


def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def is_filled(value):
    return not is_blank(value)


class SkipPage(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category  # "skipped" or "conflict"
        self.reason = reason


def clean_value(field, value):
    """The value to store, or SkipPage("skipped") if it isn't valid."""
    name = field.name
    if isinstance(field, models.PositiveSmallIntegerField):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise SkipPage("skipped", f"{name} is not a whole number")
        try:
            number = int(str(value).strip())
        except ValueError:
            raise SkipPage("skipped", f"{name} is not a whole number: {value!r}")
        if not 1 <= number <= 32767:
            raise SkipPage("skipped", f"{name} out of range: {number}")
        return number

    if not isinstance(value, str):
        raise SkipPage("skipped", f"{name} is not a string")
    value = value.strip()

    if field.choices:
        by_value = {key: key for key, _ in field.choices}
        by_label = {str(label).lower(): key for key, label in field.choices}
        if value in by_value:
            return value
        if value.lower() in by_label:
            return by_label[value.lower()]
        raise SkipPage("skipped", f"{name}: {value!r} is not one of {sorted(by_value)}")

    if field.max_length and len(value) > field.max_length:
        raise SkipPage("skipped", f"{name} is {len(value)} chars (max {field.max_length})")
    if isinstance(field, models.URLField):
        try:
            URLValidator()(value)
        except ValidationError:
            raise SkipPage("skipped", f"{name} is not a valid URL")
    if isinstance(field, RichTextField):
        problem = html_problem(value)
        if problem:
            raise SkipPage("skipped", f"{name}: {problem}")
    return value


class Command(BaseCommand):
    help = "Import Phase 1 v2 site fields (At a Glance, accounts box, prep, sources...) from JSON."

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON file; glob patterns allowed, must match exactly one file.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
        mode.add_argument("--verify", action="store_true", help="Compare the database to the file; write nothing.")

    # ------------------------------------------------------------------ input

    def _load(self, pattern):
        matches = sorted(glob.glob(pattern))
        if len(matches) != 1:
            raise CommandError(
                f"{pattern!r} must match exactly one file; matched {len(matches)}"
                + (f": {', '.join(matches)}" if matches else ".")
            )
        path = matches[0]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        pages = data.get("pages") if isinstance(data, dict) else None
        if not isinstance(pages, list):
            raise CommandError(f"{path}: expected a top-level 'pages' list.")
        return path, pages

    # ------------------------------------------------------------- per page

    def _lookup(self, entry, pages_by_id):
        page = pages_by_id.get(entry.get("id"))
        if page is None:
            raise SkipPage("skipped", "no SacredSitePage with this id")
        if page.title != entry.get("title"):
            raise SkipPage("skipped", f"title mismatch: database has {page.title!r}")
        if page.has_unpublished_changes:
            raise SkipPage("skipped", "page has unpublished changes (draft)")
        if not page.live:
            raise SkipPage("skipped", "page is not live")
        return page

    def _plan(self, entry, page):
        """{field: new value} for fields that change. Validates everything
        first; raises SkipPage on any invalid value or conflict."""
        fields = entry.get("fields", {})
        if not isinstance(fields, dict):
            raise SkipPage("skipped", "fields is not an object")
        unknown = sorted(set(fields) - set(ALLOWED_FIELDS))
        if unknown:
            raise SkipPage("skipped", f"unknown or not importable field(s): {', '.join(unknown)}")

        cleaned = {}
        for name, value in fields.items():
            if is_blank(value):
                continue  # blank = no change
            cleaned[name] = clean_value(SacredSitePage._meta.get_field(name), value)
        if "eucharistic_kind" in cleaned and page.category != EUCHARISTIC_CATEGORY:
            raise SkipPage("skipped", "eucharistic_kind on a page that isn't a Eucharistic Miracle")

        changes, conflicts, same = {}, [], 0
        for name, value in cleaned.items():
            current = getattr(page, name)
            if current == value:
                same += 1
            elif is_filled(current):
                conflicts.append(name)
            else:
                changes[name] = value
        if conflicts:
            raise SkipPage("conflict", f"already filled with a different value: {', '.join(conflicts)}")
        return changes, same

    def _apply(self, page, changes):
        with transaction.atomic():
            for name, value in changes.items():
                setattr(page, name, value)
            page.save_revision(log_action=True).publish()

    # ---------------------------------------------------------------- verify

    def _verify(self, path, entries, pages_by_id):
        matched, mismatched, not_ready = 0, [], 0
        for entry in entries:
            if entry.get("status") != READY:
                not_ready += 1
                continue
            page = pages_by_id.get(entry.get("id"))
            problems = []
            if page is None:
                problems.append("page not found")
            else:
                if page.title != entry.get("title"):
                    problems.append("title differs")
                for name, value in (entry.get("fields") or {}).items():
                    if name not in ALLOWED_FIELDS or is_blank(value):
                        continue
                    try:
                        expected = clean_value(SacredSitePage._meta.get_field(name), value)
                    except SkipPage as skip:
                        problems.append(skip.reason)
                        continue
                    if getattr(page, name) != expected:
                        problems.append(name)
            if problems:
                mismatched.append((entry.get("id"), entry.get("title"), problems))
            else:
                matched += 1

        w = self.stdout.write
        w(f"Verify {path}")
        w(f"  Ready rows in file:            {len(entries) - not_ready}")
        w(f"  Pages matching the file:       {matched}")
        w(f"  Pages NOT matching:            {len(mismatched)}")
        for pid, title, problems in mismatched:
            w(f"    - {pid} {title}: {', '.join(problems)}")
        if mismatched:
            raise CommandError(f"{len(mismatched)} page(s) do not match the file.")

    # ------------------------------------------------------------------ main

    def handle(self, *args, **options):
        path, entries = self._load(options["path"])
        ids = [e.get("id") for e in entries if isinstance(e.get("id"), int)]
        pages_by_id = SacredSitePage.objects.in_bulk(ids)

        if options["verify"]:
            return self._verify(path, entries, pages_by_id)

        dry_run = options["dry_run"]
        totals = Counter()
        skipped = []  # (id, title, category, reason)

        w = self.stdout.write
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Importing {path}")
        for entry in entries:
            if entry.get("status") != READY:
                totals["not_ready"] += 1
                continue
            try:
                page = self._lookup(entry, pages_by_id)
                changes, same = self._plan(entry, page)
            except SkipPage as skip:
                skipped.append((entry.get("id"), entry.get("title"), skip.category, skip.reason))
                continue

            totals["already_correct"] += same
            if not changes:
                totals["unchanged"] += 1
                continue
            if not dry_run:
                self._apply(page, changes)
            totals["changed"] += 1
            totals["fields"] += len(changes)
            w(f"  {'would change' if dry_run else 'changed'} {page.pk} {page.title}: {', '.join(sorted(changes))}")

        conflicts = [s for s in skipped if s[2] == "conflict"]
        others = [s for s in skipped if s[2] != "conflict"]
        w("")
        w(f"{'Would change' if dry_run else 'Pages changed'}:  {totals['changed']}")
        w(f"Pages unchanged:      {totals['unchanged']}")
        w(f"Fields set:           {totals['fields']}")
        w(f"Already correct:      {totals['already_correct']}")
        w(f"Not ready (skipped):  {totals['not_ready']}")
        w(f"Conflicts:            {len(conflicts)}")
        for pid, title, _, reason in conflicts:
            w(f"  - {pid} {title}: {reason}")
        w(f"Skipped:              {len(others)}")
        for pid, title, _, reason in others:
            w(f"  - {pid} {title}: {reason}")
