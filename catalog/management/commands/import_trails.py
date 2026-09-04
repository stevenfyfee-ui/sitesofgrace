"""Import pilgrimage trails and the site pages they run through, from JSON.

Why JSON and not the XLSX workbook that `import_catalog` reads: a trail is a
nested thing (a route, then an ordered list of stops, some of which are pages
and some of which are not), and a spreadsheet flattens exactly the part that
matters -- the order. The files this command reads live in `catalog/data/` and
are version-controlled alongside the code, so a route's shape has a history.

The safety rule this shares with the saints importer: **an existing page's
written narrative is never overwritten.** Re-running is how you add the stops
you have since researched, not how you lose the paragraph you rewrote last
week. Blank fields on an existing page are filled; filled fields are left
alone unless you pass --overwrite and mean it.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from wagtail.models import Page

from catalog.models import (
    CANONICAL_STATUS_CHOICES,
    CATEGORY_CHOICES,
    TRAIL_COLOR_CHOICES,
    TRAIL_TYPE_CHOICES,
    TRAILS_PARENT_SLUG,
    PilgrimageTrailPage,
    SacredSitePage,
    SiteTravelSection,
    TrailStop,
)
from catalog.travel_sections import TRAVEL_SECTION_CHOICES

CATEGORY_PARENT_SLUGS = {
    "Marian Apparition": "marian-apparitions",
    "Eucharistic Miracle": "eucharistic-miracles",
    "Saints & Tombs": "saints-and-tombs",
    "Holy Land": "holy-lands",
    "Shrine & Basilica": "shrines-and-basilicas",
}

VALID_CATEGORIES = {value for value, _ in CATEGORY_CHOICES}
VALID_CANONICAL_STATUSES = {value for value, _ in CANONICAL_STATUS_CHOICES}
VALID_TRAIL_TYPES = {value for value, _ in TRAIL_TYPE_CHOICES}
VALID_TRAIL_COLORS = {value for value, _ in TRAIL_COLOR_CHOICES}
VALID_TRAVEL_KINDS = {value for value, _ in TRAVEL_SECTION_CHOICES}

# Plain text fields copied straight across, and rich text fields that get
# paragraph-wrapped on the way in.
SITE_TEXT_FIELDS = [
    "canonical_status", "locality", "country", "date_display", "feast_day",
    "summary_short", "location_link", "notes_internal",
    "quick_ideal_stay", "quick_ideal_stay_note",
    "quick_best_months", "quick_best_months_note",
    "quick_airport", "quick_airport_note",
    "quick_language", "quick_language_note",
    "quick_accessibility", "quick_accessibility_note",
]
SITE_RICH_FIELDS = ["the_story", "church_recognition", "catholic_teaching", "go_deeper"]

TRAIL_TEXT_FIELDS = [
    "region", "country", "start_point", "end_point",
    "length_display", "duration_display", "best_season", "waymarking",
    "summary_short", "official_url", "notes_internal",
]
TRAIL_RICH_FIELDS = [
    "the_story", "church_recognition", "catholic_teaching",
    "walking_the_route", "go_deeper",
]


def text(value):
    if value is None:
        return ""
    return str(value).strip()


def to_richtext(value):
    """Blank lines become paragraphs; anything already tagged is left alone."""
    body = text(value)
    if not body:
        return ""
    if body.lstrip().startswith("<"):
        return body
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


class Command(BaseCommand):
    help = "Import pilgrimage trails and their sites from a JSON file in catalog/data/."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the JSON file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run inside a transaction and roll it back; nothing is saved.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help=(
                "Replace narrative text on pages that already have some. Off by "
                "default so a re-run cannot lose editing done in the admin."
            ),
        )
        parser.add_argument(
            "--replace-stops",
            action="store_true",
            help=(
                "Rebuild an existing trail's stop list from the file. Off by "
                "default so a re-run cannot lose stops reordered in the admin. "
                "A newly created trail always gets its stops."
            ),
        )
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Create new pages unpublished, so you can review them before they go live.",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}")

        self.dry_run = options["dry_run"]
        self.overwrite = options["overwrite"]
        self.replace_stops = options["replace_stops"]
        self.live = not options["draft"]
        self.warnings = []
        self.stats = {
            "sites": {"created": 0, "updated": 0},
            "trails": {"created": 0, "updated": 0},
            "stops": {"created": 0},
        }
        self._parent_cache = {}

        with transaction.atomic():
            for row in data.get("sites", []):
                self.import_site(row)
            trails = data.get("trails", [])
            if "trail" in data:
                trails = [data["trail"]] + list(trails)
            for row in trails:
                self.import_trail(row)
            if self.dry_run:
                transaction.set_rollback(True)

        self.print_summary()

    # ------------------------------------------------------------------

    def get_parent(self, slug, label):
        if slug in self._parent_cache:
            return self._parent_cache[slug]
        parent = Page.objects.filter(slug=slug).first()
        if parent is None:
            if self.dry_run:
                self.warnings.append(
                    f"Parent page '{slug}' not found -- new {label} pages skipped in "
                    "this dry run (a real run would stop here)."
                )
                self._parent_cache[slug] = None
                return None
            raise CommandError(
                f"Parent page with slug '{slug}' not found. Create it in the page "
                "tree first, then re-run this command."
            )
        parent = parent.specific
        self._parent_cache[slug] = parent
        return parent

    def to_decimal(self, value, label, field):
        raw = text(value)
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            self.warnings.append(f"Bad {field} '{raw}' for '{label}' -- left blank.")
            return None

    def assign(self, page, field, value, is_new):
        """Write `value` unless it would clobber text that is already there."""
        if not value:
            return
        if is_new or self.overwrite or not getattr(page, field):
            setattr(page, field, value)

    # ------------------------------------------------------------------

    def import_site(self, row):
        title = text(row.get("title"))
        if not title:
            self.warnings.append("A site row has no title -- skipped.")
            return None
        slug = text(row.get("slug")) or slugify(title)

        category = text(row.get("category"))
        if category and category not in VALID_CATEGORIES:
            self.warnings.append(f"Unknown category '{category}' for '{title}' -- left blank.")
            category = ""

        canonical_status = text(row.get("canonical_status"))
        if canonical_status and canonical_status not in VALID_CANONICAL_STATUSES:
            self.warnings.append(
                f"Unknown canonical_status '{canonical_status}' for '{title}' -- left blank."
            )
            row = dict(row, canonical_status="")

        site = SacredSitePage.objects.filter(slug=slug).first()
        is_new = site is None

        if is_new:
            parent_slug = text(row.get("parent_slug")) or CATEGORY_PARENT_SLUGS.get(category)
            if not parent_slug:
                self.warnings.append(
                    f"Skipped creating '{title}' -- no parent page for category '{category}'."
                )
                return None
            parent = self.get_parent(parent_slug, "site")
            if parent is None:
                return None
            site = SacredSitePage(title=title, slug=slug, live=self.live)
            site.category = category
        elif category and (self.overwrite or not site.category):
            site.category = category

        for field in SITE_TEXT_FIELDS:
            self.assign(site, field, text(row.get(field)), is_new)
        for field in SITE_RICH_FIELDS:
            self.assign(site, field, to_richtext(row.get(field)), is_new)

        latitude = self.to_decimal(row.get("latitude"), title, "latitude")
        longitude = self.to_decimal(row.get("longitude"), title, "longitude")
        if latitude is not None and (is_new or self.overwrite or site.latitude is None):
            site.latitude = latitude
        if longitude is not None and (is_new or self.overwrite or site.longitude is None):
            site.longitude = longitude

        if is_new:
            parent.add_child(instance=site)
        else:
            site.save()

        self.import_travel_sections(site, row.get("travel_sections") or [])
        self.stats["sites"]["created" if is_new else "updated"] += 1
        return site

    def import_travel_sections(self, site, rows):
        """One panel per kind. An existing panel is left exactly as it is.

        The unique (page, kind) constraint means a second panel of the same
        kind is an IntegrityError, not a duplicate -- so this checks first
        rather than relying on the database to tell it.
        """
        for row in rows:
            kind = text(row.get("kind"))
            if kind not in VALID_TRAVEL_KINDS:
                self.warnings.append(
                    f"Unknown travel section '{kind}' for '{site.title}' -- skipped."
                )
                continue
            body = to_richtext(row.get("body"))
            if not body:
                continue
            existing = SiteTravelSection.objects.filter(page=site, kind=kind).first()
            if existing is not None:
                if self.overwrite:
                    existing.body = body
                    existing.teaser = text(row.get("teaser"))
                    existing.save()
                continue
            SiteTravelSection.objects.create(
                page=site, kind=kind, body=body, teaser=text(row.get("teaser"))
            )

    # ------------------------------------------------------------------

    def import_trail(self, row):
        title = text(row.get("title"))
        if not title:
            self.warnings.append("A trail row has no title -- skipped.")
            return
        slug = text(row.get("slug")) or slugify(title)

        trail = PilgrimageTrailPage.objects.filter(slug=slug).first()
        is_new = trail is None

        if is_new:
            parent = self.get_parent(
                text(row.get("parent_slug")) or TRAILS_PARENT_SLUG, "trail"
            )
            if parent is None:
                return
            trail = PilgrimageTrailPage(title=title, slug=slug, live=self.live)

        trail_type = text(row.get("trail_type"))
        if trail_type and trail_type not in VALID_TRAIL_TYPES:
            self.warnings.append(f"Unknown trail_type '{trail_type}' for '{title}' -- default kept.")
            trail_type = ""
        if trail_type:
            trail.trail_type = trail_type

        line_color = text(row.get("line_color"))
        if line_color and line_color not in VALID_TRAIL_COLORS:
            self.warnings.append(f"Unknown line_color '{line_color}' for '{title}' -- default kept.")
            line_color = ""
        if line_color:
            trail.line_color = line_color

        for field in TRAIL_TEXT_FIELDS:
            self.assign(trail, field, text(row.get(field)), is_new)
        for field in TRAIL_RICH_FIELDS:
            self.assign(trail, field, to_richtext(row.get(field)), is_new)

        if is_new:
            parent.add_child(instance=trail)
        else:
            trail.save()

        self.stats["trails"]["created" if is_new else "updated"] += 1
        self.import_stops(trail, row.get("stops") or [], is_new)

    def import_stops(self, trail, rows, is_new):
        if not rows:
            return
        if not is_new and not self.replace_stops:
            if trail.stops.exists():
                self.warnings.append(
                    f"'{trail.title}' already has stops -- left untouched. "
                    "Pass --replace-stops to rebuild them from the file."
                )
                return
        else:
            trail.stops.all().delete()

        for index, row in enumerate(rows):
            site = None
            site_slug = text(row.get("site"))
            if site_slug:
                site = SacredSitePage.objects.filter(slug=site_slug).first()
                if site is None:
                    self.warnings.append(
                        f"Stop {index + 1} of '{trail.title}': no site page with slug "
                        f"'{site_slug}'. Kept as a waypoint if it has a name, else skipped."
                    )
            name = text(row.get("name"))
            if site is None and not name:
                self.warnings.append(
                    f"Stop {index + 1} of '{trail.title}' has neither a site nor a name -- skipped."
                )
                continue

            TrailStop.objects.create(
                trail=trail,
                sort_order=index,
                site=site,
                waypoint_name="" if site else name,
                waypoint_locality="" if site else text(row.get("locality")),
                waypoint_latitude=None if site else self.to_decimal(
                    row.get("latitude"), name or trail.title, "latitude"
                ),
                waypoint_longitude=None if site else self.to_decimal(
                    row.get("longitude"), name or trail.title, "longitude"
                ),
                note=text(row.get("note")),
                distance_display=text(row.get("distance_display")),
            )
            self.stats["stops"]["created"] += 1

    # ------------------------------------------------------------------

    def print_summary(self):
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("Dry run -- transaction rolled back, nothing was saved.\n")
            )
        self.stdout.write(
            "sites: {created} created, {updated} updated".format(**self.stats["sites"])
        )
        self.stdout.write(
            "trails: {created} created, {updated} updated".format(**self.stats["trails"])
        )
        self.stdout.write("stops: {created} created".format(**self.stats["stops"]))
        if self.warnings:
            self.stdout.write(self.style.WARNING(f"\n{len(self.warnings)} warning(s):"))
            for warning in self.warnings:
                self.stdout.write(self.style.WARNING(f"  - {warning}"))
        else:
            self.stdout.write("\n0 warnings")
