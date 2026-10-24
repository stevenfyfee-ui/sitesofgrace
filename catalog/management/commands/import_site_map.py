"""Bulk-load "Where to Stay & Map" points and lodging onto SacredSitePages.

    python manage.py import_site_map tools/*site_map*.json --dry-run
    python manage.py import_site_map tools/*site_map*.json
    python manage.py import_site_map tools/*site_map*.json --verify

Follows docs/v2/IMPORT-RULES.md. Format (see tools/site_map_example.json):

    {"pages": [{"id": 123, "title": "...", "status": "Ready to import",
                "map_points": [{"name", "kind", "latitude", "longitude",
                                "note"?, "linked_page"? (page id), "verified"?}],
                "lodging": [{"name", "kind", "latitude", "longitude", "website"?,
                             "booking_url"?, "is_affiliate_link"?, "nearest_point"?
                             (the name of an entrance on this page), "walk_minutes"?,
                             "walk_miles"?, "slope"?, "step_free"?, "note"?,
                             "route_geojson"? (a LineString object or string),
                             "verified_on"? (YYYY-MM-DD)}]}]}

Rows are matched to existing ones by (page, name). A new name creates a row
(kind, latitude and longitude required). On an existing row, a blank value
changes nothing, an empty field is filled, the same value is already correct,
and a different value is a conflict that skips the whole page (Standing
Rule 4). A boolean can only be switched on from its default; switching one
off is a conflict.
"""
import glob
import json
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import models, transaction
from wagtail.models import Page

from catalog.models import (
    ENTRANCE_KINDS, SacredSitePage, SiteLodging, SiteMapPoint, parse_route_geojson,
)

READY = "Ready to import"

POINT_FIELDS = ["kind", "latitude", "longitude", "note", "linked_page", "verified"]
LODGING_FIELDS = [
    "kind", "latitude", "longitude", "website", "booking_url", "is_affiliate_link", "nearest_point",
    "walk_minutes", "walk_miles", "slope", "step_free", "note", "route_geojson", "verified_on",
]
REQUIRED_NEW = ("kind", "latitude", "longitude")


def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


class SkipPage(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category
        self.reason = reason


def clean_value(model, name, value, where):
    """The value to store for model.<name>, or SkipPage. nearest_point stays a
    name here and is resolved per page."""
    if name == "nearest_point":
        if not isinstance(value, str):
            raise SkipPage("skipped", f"{where}: nearest_point must be an entrance name")
        return value.strip()
    if name == "linked_page":
        if isinstance(value, bool) or not str(value).strip().isdigit():
            raise SkipPage("skipped", f"{where}: linked_page must be a page id")
        page = Page.objects.filter(pk=int(value)).first()
        if page is None:
            raise SkipPage("skipped", f"{where}: linked_page {value} does not exist")
        return page
    if name == "route_geojson":
        try:
            parse_route_geojson(value)
        except ValidationError as exc:
            raise SkipPage("skipped", f"{where}: route_geojson: {exc.messages[0]}")
        return value if isinstance(value, str) else json.dumps(value)

    field = model._meta.get_field(name)
    if isinstance(field, models.BooleanField):
        if not isinstance(value, bool):
            raise SkipPage("skipped", f"{where}: {name} must be true or false")
        return value
    if isinstance(field, models.DecimalField):
        try:
            number = Decimal(str(value)).quantize(Decimal(1).scaleb(-field.decimal_places))
        except (InvalidOperation, ValueError):
            raise SkipPage("skipped", f"{where}: {name} is not a number")
        if number.adjusted() + 1 > field.max_digits - field.decimal_places:
            raise SkipPage("skipped", f"{where}: {name} is too large")
        for validator in field.validators:
            try:
                validator(number)
            except ValidationError:
                raise SkipPage("skipped", f"{where}: {name} {number} is out of range")
        return number
    if isinstance(field, models.PositiveSmallIntegerField):
        if isinstance(value, bool) or not str(value).strip().isdigit():
            raise SkipPage("skipped", f"{where}: {name} must be a whole number")
        return int(value)
    if isinstance(field, models.DateField):
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            raise SkipPage("skipped", f"{where}: {name} must be YYYY-MM-DD")
    if not isinstance(value, str):
        raise SkipPage("skipped", f"{where}: {name} is not a string")
    value = value.strip()
    if field.choices:
        by_value = {key for key, _ in field.choices}
        by_label = {str(label).lower(): key for key, label in field.choices}
        if value in by_value:
            return value
        if value.lower() in by_label:
            return by_label[value.lower()]
        raise SkipPage("skipped", f"{where}: {name} {value!r} is not one of {sorted(by_value)}")
    if field.max_length and len(value) > field.max_length:
        raise SkipPage("skipped", f"{where}: {name} is {len(value)} chars (max {field.max_length})")
    if isinstance(field, models.URLField):
        try:
            URLValidator()(value)
        except ValidationError:
            raise SkipPage("skipped", f"{where}: {name} is not a valid URL")
    return value


def current_value(obj, name):
    if name == "nearest_point":
        return obj.nearest_point.name if obj.nearest_point_id else None
    if name == "linked_page":
        return obj.linked_page if obj.linked_page_id else None
    return getattr(obj, name)


def same(name, current, new):
    if name == "route_geojson" and current:
        try:
            return parse_route_geojson(current) == parse_route_geojson(new)
        except ValidationError:
            return False
    return current == new


class Command(BaseCommand):
    help = "Import Where to Stay & Map points and lodging from JSON (docs/v2/IMPORT-RULES.md)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON file; glob patterns allowed, must match exactly one file.")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
        mode.add_argument("--verify", action="store_true", help="Compare the database to the file; write nothing.")

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

    # ------------------------------------------------------------------ plan

    def _plan_rows(self, model, rows, existing, allowed, label):
        """[(obj or None, name, {field: value})], counts. Validates all rows."""
        if not isinstance(rows, list):
            raise SkipPage("skipped", f"{label} is not a list")
        plan, counts, seen = [], Counter(), set()
        for row in rows:
            if not isinstance(row, dict) or is_blank(row.get("name")):
                raise SkipPage("skipped", f"{label}: every row needs a name")
            name = row["name"].strip()
            where = f"{label} {name!r}"
            if name in seen:
                raise SkipPage("skipped", f"{where} appears twice")
            seen.add(name)
            if len(name) > model._meta.get_field("name").max_length:
                raise SkipPage("skipped", f"{where}: name is too long")
            unknown = sorted(set(row) - set(allowed) - {"name"})
            if unknown:
                raise SkipPage("skipped", f"{where}: unknown field(s) {', '.join(unknown)}")
            values = {k: clean_value(model, k, v, where) for k, v in row.items()
                      if k != "name" and not is_blank(v)}
            obj = existing.get(name)
            if obj is None:
                missing = [f for f in REQUIRED_NEW if f not in values]
                if missing:
                    raise SkipPage("skipped", f"{where}: a new row needs {', '.join(missing)}")
                plan.append((None, name, values))
                counts["created"] += 1
                continue
            changes = {}
            for field, value in values.items():
                current = current_value(obj, field)
                if same(field, current, value):
                    counts["same"] += 1
                elif current in (None, "", False):
                    changes[field] = value
                else:
                    raise SkipPage("conflict", f"{where}: {field} already filled with a different value")
            if changes:
                plan.append((obj, name, changes))
                counts["updated"] += 1
        return plan, counts

    def _plan(self, entry, page):
        points = {p.name: p for p in page.map_points.all()}
        lodgings = {lodging.name: lodging for lodging in page.lodgings.select_related("nearest_point")}
        point_plan, point_counts = self._plan_rows(
            SiteMapPoint, entry.get("map_points", []), points, POINT_FIELDS, "map point")
        lodging_plan, lodging_counts = self._plan_rows(
            SiteLodging, entry.get("lodging", []), lodgings, LODGING_FIELDS, "lodging")

        # nearest_point must name an entrance on this page (existing or in this file).
        entrance_kinds = {name: p.kind for name, p in points.items()}
        for obj, name, values in point_plan:
            if "kind" in values:
                entrance_kinds[name] = values["kind"]
        for _, name, values in lodging_plan:
            target = values.get("nearest_point")
            if target is not None and entrance_kinds.get(target) not in ENTRANCE_KINDS:
                raise SkipPage("skipped", f"lodging {name!r}: nearest_point {target!r} is not an entrance on this page")
        return point_plan, lodging_plan, point_counts, lodging_counts

    # ----------------------------------------------------------------- apply

    def _apply(self, page, point_plan, lodging_plan):
        with transaction.atomic():
            points = list(page.map_points.all())
            by_name = {p.name: p for p in points}
            for _, name, values in point_plan:
                target = by_name.get(name)
                if target is None:
                    target = by_name[name] = SiteMapPoint(name=name)
                    points.append(target)
                for field, value in values.items():
                    setattr(target, field, value)
            if point_plan:
                page.map_points = points
                # Commit the points first so lodging can point at them by id;
                # the page has no draft, so its row already equals the live page.
                page.save()
                by_name = {p.name: p for p in page.map_points.all()}

            lodgings = list(page.lodgings.all())
            lodging_by_name = {lodging.name: lodging for lodging in lodgings}
            for _, name, values in lodging_plan:
                target = lodging_by_name.get(name)
                if target is None:
                    target = lodging_by_name[name] = SiteLodging(name=name)
                    lodgings.append(target)
                for field, value in values.items():
                    setattr(target, field, by_name[value] if field == "nearest_point" else value)
            if lodging_plan:
                page.lodgings = lodgings
            page.save_revision(log_action=True).publish()

    # ---------------------------------------------------------------- verify

    def _verify(self, path, entries, pages_by_id):
        matched, mismatched = 0, []
        for entry in entries:
            if entry.get("status") != READY:
                continue
            page = pages_by_id.get(entry.get("id"))
            problems = []
            if page is None:
                problems.append("page not found")
            else:
                for model, key, allowed, related in (
                    (SiteMapPoint, "map_points", POINT_FIELDS, page.map_points.all()),
                    (SiteLodging, "lodging", LODGING_FIELDS, page.lodgings.select_related("nearest_point")),
                ):
                    existing = {obj.name: obj for obj in related}
                    for row in entry.get(key, []) or []:
                        name = (row.get("name") or "").strip()
                        obj = existing.get(name)
                        if obj is None:
                            problems.append(f"{name} missing")
                            continue
                        for field, value in row.items():
                            if field == "name" or field not in allowed or is_blank(value):
                                continue
                            try:
                                expected = clean_value(model, field, value, name)
                            except SkipPage as skip:
                                problems.append(skip.reason)
                                continue
                            if not same(field, current_value(obj, field), expected):
                                problems.append(f"{name} {field}")
            if problems:
                mismatched.append((entry.get("id"), entry.get("title"), problems))
            else:
                matched += 1
        w = self.stdout.write
        w(f"Verify {path}")
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
        skipped = []
        w = self.stdout.write
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Importing {path}")
        for entry in entries:
            if entry.get("status") != READY:
                totals["not_ready"] += 1
                continue
            try:
                page = self._lookup(entry, pages_by_id)
                point_plan, lodging_plan, pc, lc = self._plan(entry, page)
            except SkipPage as skip:
                skipped.append((entry.get("id"), entry.get("title"), skip.category, skip.reason))
                continue
            totals["already_correct"] += pc["same"] + lc["same"]
            if not point_plan and not lodging_plan:
                totals["unchanged"] += 1
                continue
            if not dry_run:
                self._apply(page, point_plan, lodging_plan)
            totals["changed"] += 1
            for key in ("created", "updated"):
                totals[f"points_{key}"] += pc[key]
                totals[f"lodging_{key}"] += lc[key]
            w(f"  {'would change' if dry_run else 'changed'} {page.pk} {page.title}: "
              f"points +{pc['created']} ~{pc['updated']}, lodging +{lc['created']} ~{lc['updated']}")

        conflicts = [s for s in skipped if s[2] == "conflict"]
        others = [s for s in skipped if s[2] != "conflict"]
        w("")
        w(f"{'Would change' if dry_run else 'Pages changed'}:  {totals['changed']}")
        w(f"Pages unchanged:      {totals['unchanged']}")
        w(f"Map points created:   {totals['points_created']}")
        w(f"Map points updated:   {totals['points_updated']}")
        w(f"Lodging created:      {totals['lodging_created']}")
        w(f"Lodging updated:      {totals['lodging_updated']}")
        w(f"Already correct:      {totals['already_correct']}")
        w(f"Not ready (skipped):  {totals['not_ready']}")
        w(f"Conflicts:            {len(conflicts)}")
        for pid, title, _, reason in conflicts:
            w(f"  - {pid} {title}: {reason}")
        w(f"Skipped:              {len(others)}")
        for pid, title, _, reason in others:
            w(f"  - {pid} {title}: {reason}")
