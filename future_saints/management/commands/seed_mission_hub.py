"""Fill the California Missions hub's 21 MissionHubEntry rows from the founding-order file.

    python manage.py seed_mission_hub --dry-run
    python manage.py seed_mission_hub

Each entry in docs/future-saints/content/missions-founding-order.json is matched
to its canonical SacredSitePage through the California Mission Trail's stops:
both names are normalized (accents, case, "Mission", "de", "la" and punctuation
removed) and every word of the file's name must appear in the page title. Zero
or two-plus matches stop that entry; nothing is guessed. The older duplicate
pages #1144 and #1126 are never used.

The dry run prints one row per mission: founding #, the file's name, the
canonical id and exact title, latitude/longitude, the canonical founding text,
and YEAR MATCH (the file's year against the year in that text). A mismatch is
reported, never fixed. Mission Dolores (#6, dedication vs founding date) and a
year-only founding text (San Juan Capistrano, #7) are flagged from the Phase 0
audit.

Writes only when all 21 entries resolve, as a new DRAFT revision of the
California Missions index (never published; an editor publishes in the admin).
Badge offsets and review flags already set on a mission are kept; where none is
set, the reviewed BADGE_OFFSETS (future_saints.missions) are written, marked
reviewed. Never writes into any adult page. A second run with nothing changed
writes nothing.
"""
import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import PilgrimageTrailPage
from future_saints.learning import MISSION_TRAIL_SLUG
from future_saints.missions import BADGE_OFFSETS, MISSION_COUNT, MissionHubEntry, normalize_mission_name
from future_saints.models import FutureSaintsIndexPage

FORMAT = "future-saints-mission-founding-order/v1"
DEFAULT_PATH = "docs/future-saints/content/missions-founding-order.json"
EXCLUDED_DUPLICATES = {1144, 1126}
YEAR = re.compile(r"\b(1[6-9]\d\d)\b")
FOUNDED_PREFIX = re.compile(r"^\s*founded\s*:?\s*", re.IGNORECASE)
AUDIT_FLAGS = {
    6: "Mission Dolores: this date may be the formal dedication (October 9, 1776), not the founding "
       "(late June 1776 in many sources). Verify against a primary source before a child page uses it.",
}


class Command(BaseCommand):
    help = "Fill the California Missions hub's 21 missions from the founding-order file (draft revision)."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
        parser.add_argument("--dry-run", action="store_true", help="Match and report; write nothing.")

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != FORMAT:
            raise CommandError(f'"format" must be "{FORMAT}".')
        rows = data.get("missions") or []
        numbers = [r.get("founding_number") for r in rows]
        if sorted(numbers) != list(range(1, MISSION_COUNT + 1)):
            raise CommandError(f"the file must list founding numbers 1–{MISSION_COUNT} once each (got {numbers})")

        hubs = list(FutureSaintsIndexPage.objects.filter(content_kind="california_mission"))
        if len(hubs) != 1:
            raise CommandError(f"need exactly one California Missions index (found {len(hubs)})")
        hub = hubs[0]
        trail = PilgrimageTrailPage.objects.filter(slug=MISSION_TRAIL_SLUG).first()
        if trail is None:
            raise CommandError(f'no trail with slug "{MISSION_TRAIL_SLUG}"')
        sites = [stop.site for stop in trail.stops.select_related("site")
                 if stop.site is not None and stop.site.live and stop.site.pk not in EXCLUDED_DUPLICATES]
        words = {site.pk: set(normalize_mission_name(site.title)) for site in sites}

        self.stdout.write(f"{'DRY RUN' if options['dry_run'] else 'SEED'}: {options['path']} -> "
                          f"{hub.url_path} (#{hub.pk}); {len(sites)} live Mission Trail stop page(s); "
                          f"excluded duplicates: {', '.join(f'#{pk}' for pk in sorted(EXCLUDED_DUPLICATES))}")
        self.stdout.write(f"{'#':>2} | {'file name':38} | {'canonical id + exact title':58} | {'lat, lng':21} | "
                          f"{'canonical founding text':28} | year match")
        wanted, failures, flags, used = [], [], [], {}
        for row in sorted(rows, key=lambda r: r["founding_number"]):
            n, name, year = row["founding_number"], row.get("name", ""), row.get("founded_year")
            need = set(normalize_mission_name(name))
            matches = [s for s in sites if need and need <= words[s.pk]]
            if len(matches) != 1:
                found = "; ".join(f"#{s.pk} {s.title!r}" for s in matches) or "none"
                failures.append(f"#{n} {name!r}: {len(matches)} match(es) ({found}); entry stopped, nothing guessed")
                self.stdout.write(f"{n:>2} | {name:38} | {'NO SINGLE MATCH: ' + str(len(matches)):58} |")
                continue
            site = matches[0]
            if site.pk in used:
                failures.append(f"#{n} {name!r}: #{site.pk} already matched #{used[site.pk]}")
                continue
            used[site.pk] = n
            text = site.date_display or ""
            years = YEAR.findall(text)
            match = "yes" if years and int(years[0]) == year else f"NO (file {year}, page {years[0] if years else 'none'})"
            if match != "yes":
                flags.append(f"#{n}: year mismatch: file {year}, canonical text {text!r} (reported, not fixed)")
            display = FOUNDED_PREFIX.sub("", text).strip()
            if re.fullmatch(r"\d{4}", display):
                flags.append(f"#{n} {site.title}: the founding text is year only ({text!r}); a full date needs a source")
            if n in AUDIT_FLAGS:
                flags.append(f"#{n} {site.title}: {AUDIT_FLAGS[n]} (canonical text {text!r})")
            if site.latitude is None or site.longitude is None:
                failures.append(f"#{n} #{site.pk} {site.title!r} has no latitude/longitude; it can't be placed")
            latlng = f"{site.latitude}, {site.longitude}"
            self.stdout.write(f"{n:>2} | {name:38} | {f'#{site.pk} {site.title}':58} | {latlng:21} | {text:28} | {match}")
            wanted.append({"founding_number": n, "canonical_id": site.pk, "founded_year": year, "founded_display": display})

        for line in flags:
            self.stdout.write(self.style.WARNING(f"  flag: {line}"))
        if failures:
            for line in failures:
                self.stdout.write(self.style.ERROR(f"  FAILED {line}"))
            raise CommandError(f"{len(failures)} entr(y/ies) didn't resolve; nothing was written.")

        latest = hub.get_latest_revision_as_object() if hub.get_latest_revision() else hub
        kept = {e.canonical_id: e for e in latest.mission_hub_entries.all()}
        for w in wanted:
            old = kept.get(w["canonical_id"])
            if old is not None and (old.map_offset_x is not None or old.map_offset_y is not None):
                w.update(map_offset_x=old.map_offset_x, map_offset_y=old.map_offset_y, needs_review=old.needs_review)
            else:
                dx, dy = BADGE_OFFSETS.get(w["founding_number"], (0, 0))
                w.update(map_offset_x=float(dx), map_offset_y=float(dy), needs_review=False)
        have = [{"founding_number": e.founding_number, "canonical_id": e.canonical_id, "founded_year": e.founded_year,
                 "founded_display": e.founded_display, "map_offset_x": e.map_offset_x, "map_offset_y": e.map_offset_y,
                 "needs_review": e.needs_review}
                for e in sorted(latest.mission_hub_entries.all(), key=lambda e: e.founding_number)]
        if have == wanted:
            self.stdout.write(self.style.SUCCESS(f"Unchanged: all {MISSION_COUNT} missions already match (no revision)."))
            return
        if options["dry_run"]:
            self.stdout.write(f"Would save a draft revision of {hub.url_path} with {len(wanted)} missions "
                              f"({len(have)} now). Nothing is published.")
            return
        with transaction.atomic():
            entries = [MissionHubEntry(sort_order=i, **w) for i, w in enumerate(wanted)]
            latest.mission_hub_entries = entries
            latest.save_revision(log_action=True)
        self.stdout.write(self.style.SUCCESS(
            f"Saved a draft revision of {hub.url_path} with {len(wanted)} missions. Nothing is published; "
            "an editor publishes the index in the admin."))
