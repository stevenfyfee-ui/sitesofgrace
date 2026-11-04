"""Load destinations' curated plan days from JSON.

    python manage.py import_plan_days tools/imports/plan_days_2026-11.json --dry-run
    python manage.py import_plan_days tools/imports/plan_days_2026-11.json
    python manage.py import_plan_days tools/imports/plan_days_2026-11.json --verify

    {"destinations": [
        {"slug": "rome-vatican-city",
         "gateway_airport_iata": "FCO",
         "days": [
            {"title": "St. Peter's and the Vatican",
             "sites": ["st-peters-basilica"],
             "extra_places": "Vatican Museums; Scavi tour (book ahead)"}]}]}

Follows docs/v2/IMPORT-RULES.md, with these differences for snippet rows:
rows are keyed on destination slug plus day order (a day's position in
"days": first = day 1), not on a page ID; "status" is optional, but when
present only "Ready to import" is used. Sites are live sacred site page
slugs; an unknown, non-live or ambiguous slug skips the whole destination
and is listed. gateway_airport_iata / gateway_airport_name are optional.

Idempotent: a day already stored with the same title, sites and extra
places is unchanged. A day stored at that order with anything different, or
a gateway already set to something else, is a conflict and skips the
destination (edit it in the admin). New days are added. Blank means no
change; days are never deleted.
"""
import glob
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SacredSitePage
from planner.models import DestinationCost, DestinationPlanDay

READY = "Ready to import"
DEST_KEYS = {"slug", "status", "gateway_airport_iata", "gateway_airport_name", "days"}
GATEWAY_FIELDS = ("gateway_airport_iata", "gateway_airport_name")
DAY_KEYS = {"title", "sites", "extra_places"}


class SkipDestination(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category
        self.reason = reason


def _max(model, name):
    return model._meta.get_field(name).max_length


def stored_sites(day):
    """A day's site ids in the order they were added."""
    through = DestinationPlanDay.sites.through
    return list(through.objects.filter(destinationplanday=day).order_by("id")
                .values_list("sacredsitepage_id", flat=True))


def clean_gateway(entry, dest):
    """{field: value} to set. Blank is no change; a different filled value is a conflict."""
    out = {}
    for name in GATEWAY_FIELDS:
        value = entry.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not isinstance(value, str):
            raise SkipDestination("skipped", f"{name} must be text")
        value = value.strip().upper() if name == "gateway_airport_iata" else value.strip()
        if len(value) > _max(DestinationCost, name):
            raise SkipDestination("skipped", f"{name} is longer than {_max(DestinationCost, name)} characters")
        current = getattr(dest, name) or ""
        if current == value:
            continue
        if current:
            raise SkipDestination("conflict", f"{name} is already {current!r}")
        out[name] = value
    return out


def clean_days(raw_days, live_by_slug):
    if not isinstance(raw_days, list) or not raw_days:
        raise SkipDestination("skipped", "days must be a non-empty list")
    days, unknown = [], []
    for order, raw in enumerate(raw_days, start=1):
        if not isinstance(raw, dict):
            raise SkipDestination("skipped", f"day {order} must be an object")
        extra_keys = sorted(set(raw) - DAY_KEYS)
        if extra_keys:
            raise SkipDestination("skipped", f"day {order}: unknown field(s): {', '.join(extra_keys)}")
        title = (raw.get("title") or "").strip()
        if not title:
            raise SkipDestination("skipped", f"day {order}: title is required")
        if len(title) > _max(DestinationPlanDay, "title"):
            raise SkipDestination("skipped", f"day {order}: title is longer than "
                                             f"{_max(DestinationPlanDay, 'title')} characters")
        extra = (raw.get("extra_places") or "").strip()
        if len(extra) > _max(DestinationPlanDay, "extra_places"):
            raise SkipDestination("skipped", f"day {order}: extra_places is longer than "
                                             f"{_max(DestinationPlanDay, 'extra_places')} characters")
        slugs = raw.get("sites") or []
        if not isinstance(slugs, list) or not all(isinstance(s, str) for s in slugs):
            raise SkipDestination("skipped", f"day {order}: sites must be a list of slugs")
        site_ids = []
        for slug in slugs:
            pages = live_by_slug.get(slug.strip(), [])
            if len(pages) != 1:
                unknown.append(slug if not pages else f"{slug} (ambiguous: {len(pages)} live pages)")
            elif pages[0] not in site_ids:
                site_ids.append(pages[0])
        days.append({"order": order, "title": title, "extra": extra, "site_ids": site_ids})
    if unknown:
        raise SkipDestination("skipped", "unknown or non-live site slug(s): " + ", ".join(unknown))
    return days


class Command(BaseCommand):
    help = "Import curated plan days for planner destinations (docs/v2/IMPORT-RULES.md)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="JSON file (glob allowed; must match exactly one file).")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
        mode.add_argument("--verify", action="store_true", help="Check the database matches the file.")

    def handle(self, *args, **options):
        matches = sorted(glob.glob(options["path"]))
        if len(matches) != 1:
            raise CommandError(f"{options['path']!r} must match exactly one file; it matched {len(matches)}.")
        try:
            with open(matches[0], encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CommandError(f"Can't read {matches[0]}: {exc}")
        entries = data.get("destinations") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise CommandError('The file needs a top-level "destinations" list.')

        live_by_slug = {}
        for pk, slug in SacredSitePage.objects.live().values_list("pk", "slug"):
            live_by_slug.setdefault(slug, []).append(pk)
        dests = {d.slug: d for d in DestinationCost.objects.all()}

        dry, verify = options["dry_run"], options["verify"]
        changed, unchanged, days_added, not_ready = [], 0, 0, 0
        problems, mismatches, seen = [], [], set()

        for entry in entries:
            slug = (entry.get("slug") or "").strip() if isinstance(entry, dict) else ""
            if not isinstance(entry, dict) or entry.get("status", READY) != READY:
                not_ready += 1
                continue
            try:
                unknown_keys = sorted(set(entry) - DEST_KEYS)
                if unknown_keys:
                    raise SkipDestination("skipped", f"unknown field(s): {', '.join(unknown_keys)}")
                if slug in seen:
                    raise SkipDestination("skipped", "appears twice in the file")
                seen.add(slug)
                dest = dests.get(slug)
                if dest is None:
                    raise SkipDestination("skipped", "no destination with this slug")
                gateway = clean_gateway(entry, dest)
                days = clean_days(entry.get("days"), live_by_slug)
                existing = {d.sort_order: d for d in dest.plan_days.all()}
                to_add = []
                for day in days:
                    current = existing.get(day["order"] - 1)
                    if current is None:
                        to_add.append(day)
                        continue
                    same = (current.title == day["title"]
                            and (current.extra_places or "") == day["extra"]
                            and stored_sites(current) == day["site_ids"])
                    if not same:
                        raise SkipDestination("conflict", f"day {day['order']} is already "
                                                          f"\"{current.title}\" with different content")
            except SkipDestination as skip:
                problems.append((slug or "?", skip.category, skip.reason))
                continue

            if verify:
                missing = [f"day {d['order']}" for d in to_add] + list(gateway)
                if missing:
                    mismatches.append(f"{slug}: missing {', '.join(missing)}")
                continue
            if not to_add and not gateway:
                unchanged += 1
                continue
            parts = []
            if to_add:
                parts.append(f"+{len(to_add)} day(s) ({', '.join(str(d['order']) for d in to_add)})")
            if gateway:
                parts.append(", ".join(f"{k}={v}" for k, v in gateway.items()))
            changed.append(f"{slug}: {'; '.join(parts)}")
            days_added += len(to_add)
            if dry:
                continue
            with transaction.atomic():
                if gateway:
                    for name, value in gateway.items():
                        setattr(dest, name, value)
                    dest.save(update_fields=list(gateway))
                through = DestinationPlanDay.sites.through
                for day in to_add:
                    row = DestinationPlanDay.objects.create(
                        destination=dest, sort_order=day["order"] - 1, title=day["title"],
                        extra_places=day["extra"] or None,
                    )
                    for site_id in day["site_ids"]:
                        through.objects.create(destinationplanday=row, sacredsitepage_id=site_id)

        if verify:
            for slug, category, reason in problems:
                mismatches.append(f"{slug}: {category}: {reason}")
            if mismatches:
                raise CommandError("Doesn't match the file:\n  " + "\n  ".join(mismatches))
            self.stdout.write("Verified: every destination's days match the file.")
            return

        verb = "[dry run] would change" if dry else "Changed"
        for line in changed:
            self.stdout.write(f"{verb} {line}")
        self.stdout.write(
            f"\nChanged: {len(changed)}   Unchanged: {unchanged}   Days added: {days_added}   "
            f"Conflicts: {sum(1 for p in problems if p[1] == 'conflict')}   "
            f"Skipped: {sum(1 for p in problems if p[1] == 'skipped')}   Not ready: {not_ready}"
        )
        for slug, category, reason in problems:
            self.stdout.write(f"  - {slug}: {category}: {reason}")
