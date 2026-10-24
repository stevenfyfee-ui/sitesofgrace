"""Bulk-load destination hub text and orderables from JSON.

    python manage.py import_hubs tools/*hubs*.json --dry-run
    python manage.py import_hubs tools/*hubs*.json
    python manage.py import_hubs tools/*hubs*.json --verify

Follows docs/v2/IMPORT-RULES.md, with one addition for hubs that aren't
live yet (see "Pages that aren't live yet" there): their new values are
saved as a new draft revision and the hub stays unpublished. Live hubs are
published as usual, and live hubs with a draft are skipped.

    {"pages": [{"id": 1234, "title": "Assisi & Umbria", "status": "Ready to import",
                "fields": {"intro": "...", "tile_caption": "...", "country_codes": ["IT"],
                           "localities": ["Assisi", "Cascia"], "include_auto": true,
                           "getting_around": "<ul><li>...</li></ul>",
                           "travel_advisory_url": "https://...", "plan_link_url": "/plan/"},
                "hub_sites": [<site page id>, ...],
                "stay_options": [{"label": "1 day", "text": "..."}],
                "combine_with": [{"site": <id>, "name": "...", "reason": "...",
                                  "travel_time": "1 h 30", "mode": "drive"}],
                "related_trails": [<trail page id>, ...]}]}

Blank = no change. A text field already filled with something else, or an
orderable list that already has different rows, is a conflict and skips
the hub; the same value is already correct.
"""
import glob
import json
from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import transaction

from catalog.countries import COUNTRY_NAMES
from catalog.management.commands.import_saints import html_problem
from catalog.models import PilgrimageTrailPage, SacredSitePage
from destinations.models import (
    COMBINE_MODE_CHOICES, CombineWith, DestinationHubPage, HubSite, StayOption,
)

READY = "Ready to import"
TEXT_FIELDS = ["intro", "tile_caption", "getting_around", "travel_advisory_url", "plan_link_url"]
OTHER_FIELDS = ["country_codes", "localities", "include_auto"]
MODES = {key for key, _ in COMBINE_MODE_CHOICES}


def is_blank(value):
    return value is None or value == [] or (isinstance(value, str) and value.strip() == "")


class SkipPage(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category
        self.reason = reason


def _max(model, name):
    return model._meta.get_field(name).max_length


def clean_fields(fields):
    if not isinstance(fields, dict):
        raise SkipPage("skipped", "fields is not an object")
    unknown = sorted(set(fields) - set(TEXT_FIELDS) - set(OTHER_FIELDS))
    if unknown:
        raise SkipPage("skipped", f"unknown field(s): {', '.join(unknown)}")
    out = {}
    for name, value in fields.items():
        if is_blank(value):
            continue
        if name == "country_codes":
            codes = [str(c).strip().upper() for c in (value if isinstance(value, list) else [value])]
            bad = [c for c in codes if c not in COUNTRY_NAMES]
            if bad:
                raise SkipPage("skipped", f"country_codes: not ISO codes: {', '.join(bad)}")
            out[name] = codes
        elif name == "localities":
            lines = value if isinstance(value, list) else str(value).splitlines()
            out[name] = "\n".join(str(v).strip() for v in lines if str(v).strip())
        elif name == "include_auto":
            if not isinstance(value, bool):
                raise SkipPage("skipped", "include_auto must be true or false")
            out[name] = value
        else:
            if not isinstance(value, str):
                raise SkipPage("skipped", f"{name} is not a string")
            value = value.strip()
            limit = _max(DestinationHubPage, name)
            if limit and len(value) > limit:
                raise SkipPage("skipped", f"{name} is {len(value)} chars (max {limit})")
            if name == "travel_advisory_url":
                try:
                    URLValidator()(value)
                except ValidationError:
                    raise SkipPage("skipped", "travel_advisory_url is not a valid URL")
            if name == "getting_around":
                problem = html_problem(value)
                if problem:
                    raise SkipPage("skipped", f"getting_around: {problem}")
            out[name] = value
    return out


def clean_rows(entry):
    """{relation: [plain dicts]} for the orderables in the entry."""
    rows = {}
    if not is_blank(entry.get("hub_sites")):
        ids = entry["hub_sites"]
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise SkipPage("skipped", "hub_sites must be a list of site page ids")
        found = set(SacredSitePage.objects.filter(pk__in=ids).values_list("pk", flat=True))
        missing = [i for i in ids if i not in found]
        if missing:
            raise SkipPage("skipped", f"hub_sites: no sacred site page {missing}")
        rows["hub_sites"] = [{"site_id": i} for i in ids]
    if not is_blank(entry.get("stay_options")):
        options = entry["stay_options"]
        if not isinstance(options, list) or len(options) > 3:
            raise SkipPage("skipped", "stay_options must be a list of at most 3")
        cleaned = []
        for opt in options:
            label, text = (opt.get("label") or "").strip(), (opt.get("text") or "").strip()
            if not label or not text:
                raise SkipPage("skipped", "every stay option needs a label and text")
            if len(label) > _max(StayOption, "label") or len(text) > _max(StayOption, "text"):
                raise SkipPage("skipped", f"stay option {label!r} is too long")
            cleaned.append({"label": label, "text": text})
        rows["stay_options"] = cleaned
    if not is_blank(entry.get("combine_with")):
        cleaned = []
        for trip in entry["combine_with"]:
            site_id = trip.get("site")
            if site_id is not None and not SacredSitePage.objects.filter(pk=site_id).exists():
                raise SkipPage("skipped", f"combine_with: no sacred site page {site_id}")
            row = {"site_id": site_id}
            for name in ("name", "reason", "travel_time"):
                value = (trip.get(name) or "").strip() or None
                if value and len(value) > _max(CombineWith, name):
                    raise SkipPage("skipped", f"combine_with {name} is too long")
                row[name] = value
            mode = (trip.get("mode") or "").strip() or None
            if mode and mode not in MODES:
                raise SkipPage("skipped", f"combine_with mode {mode!r} is not one of {sorted(MODES)}")
            row["mode"] = mode
            if not row["site_id"] and not row["name"]:
                raise SkipPage("skipped", "every day trip needs a site or a name")
            cleaned.append(row)
        rows["combine_with"] = cleaned
    if not is_blank(entry.get("related_trails")):
        ids = entry["related_trails"]
        found = set(PilgrimageTrailPage.objects.filter(pk__in=ids).values_list("pk", flat=True))
        missing = [i for i in ids if i not in found]
        if missing:
            raise SkipPage("skipped", f"related_trails: no trail page {missing}")
        rows["related_trails"] = sorted(ids)
    return rows


ROW_KEYS = {
    "hub_sites": ("site_id",),
    "stay_options": ("label", "text"),
    "combine_with": ("site_id", "name", "reason", "travel_time", "mode"),
}
ROW_MODELS = {"hub_sites": HubSite, "stay_options": StayOption, "combine_with": CombineWith}


def current_rows(obj, relation):
    if relation == "related_trails":
        return sorted(t.pk for t in obj.related_trails.all())
    keys = ROW_KEYS[relation]
    return [{k: getattr(row, k) for k in keys} for row in getattr(obj, relation).all()]


class Command(BaseCommand):
    help = "Import destination hub text and orderables from JSON (docs/v2/IMPORT-RULES.md)."

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
        with open(matches[0], encoding="utf-8") as fh:
            data = json.load(fh)
        pages = data.get("pages") if isinstance(data, dict) else None
        if not isinstance(pages, list):
            raise CommandError(f"{matches[0]}: expected a top-level 'pages' list.")
        return matches[0], pages

    def _target(self, entry, hubs):
        hub = hubs.get(entry.get("id"))
        if hub is None:
            raise SkipPage("skipped", "no destination hub with this id")
        if hub.title != entry.get("title"):
            raise SkipPage("skipped", f"title mismatch: database has {hub.title!r}")
        if hub.live:
            if hub.has_unpublished_changes:
                raise SkipPage("skipped", "live hub has unpublished changes (draft)")
            return hub, hub
        # Not live: work on the latest draft and save another draft.
        return hub, hub.get_latest_revision_as_object()

    def _plan(self, entry, obj):
        fields = clean_fields(entry.get("fields", {}))
        rows = clean_rows(entry)
        changes, same = {}, 0
        for name, value in fields.items():
            current = getattr(obj, name)
            if current == value:
                same += 1
            elif current in (None, "", [], False):
                changes[name] = value
            else:
                raise SkipPage("conflict", f"{name} already filled with a different value")
        row_changes = {}
        for relation, wanted in rows.items():
            current = current_rows(obj, relation)
            if current == wanted:
                same += 1
            elif not current:
                row_changes[relation] = wanted
            else:
                raise SkipPage("conflict", f"{relation} already has different rows")
        return changes, row_changes, same

    def _apply(self, hub, obj, changes, row_changes):
        with transaction.atomic():
            for name, value in changes.items():
                setattr(obj, name, value)
            for relation, wanted in row_changes.items():
                if relation == "related_trails":
                    obj.related_trails = list(PilgrimageTrailPage.objects.filter(pk__in=wanted))
                else:
                    model = ROW_MODELS[relation]
                    setattr(obj, relation, [model(sort_order=i, **row) for i, row in enumerate(wanted)])
            revision = obj.save_revision(log_action=True)
            if hub.live:
                revision.publish()

    def handle(self, *args, **options):
        path, entries = self._load(options["path"])
        ids = [e.get("id") for e in entries if isinstance(e.get("id"), int)]
        hubs = {h.pk: h for h in DestinationHubPage.objects.filter(pk__in=ids)}
        verify, dry_run = options["verify"], options["dry_run"]
        totals, skipped, mismatched = Counter(), [], []
        w = self.stdout.write
        w(("VERIFY " if verify else "DRY RUN -- nothing will be written. " if dry_run else "") + f"Importing {path}")
        for entry in entries:
            if entry.get("status") != READY:
                totals["not_ready"] += 1
                continue
            try:
                hub, obj = self._target(entry, hubs)
                changes, row_changes, same = self._plan(entry, obj)
            except SkipPage as skip:
                if verify:
                    mismatched.append((entry.get("id"), entry.get("title"), skip.reason))
                else:
                    skipped.append((entry.get("id"), entry.get("title"), skip.category, skip.reason))
                continue
            totals["already_correct"] += same
            if verify:
                if changes or row_changes:
                    mismatched.append((hub.pk, hub.title, ", ".join(sorted([*changes, *row_changes]))))
                else:
                    totals["matched"] += 1
                continue
            if not changes and not row_changes:
                totals["unchanged"] += 1
                continue
            if not dry_run:
                self._apply(hub, obj, changes, row_changes)
            totals["changed"] += 1
            totals["drafts" if not hub.live else "published"] += 1
            w(f"  {'would change' if dry_run else 'changed'} {hub.pk} {hub.title}"
              f"{'' if hub.live else ' (draft revision; stays unpublished)'}: "
              f"{', '.join(sorted([*changes, *row_changes]))}")

        if verify:
            w(f"  Hubs matching the file:        {totals['matched']}")
            w(f"  Hubs NOT matching:             {len(mismatched)}")
            for pid, title, reason in mismatched:
                w(f"    - {pid} {title}: {reason}")
            if mismatched:
                raise CommandError(f"{len(mismatched)} hub(s) do not match the file.")
            return
        conflicts = [s for s in skipped if s[2] == "conflict"]
        others = [s for s in skipped if s[2] != "conflict"]
        w("")
        w(f"{'Would change' if dry_run else 'Hubs changed'}:   {totals['changed']}")
        w(f"  as draft revisions: {totals['drafts']}")
        w(f"  published:          {totals['published']}")
        w(f"Hubs unchanged:       {totals['unchanged']}")
        w(f"Already correct:      {totals['already_correct']}")
        w(f"Not ready (skipped):  {totals['not_ready']}")
        w(f"Conflicts:            {len(conflicts)}")
        for pid, title, _, reason in conflicts:
            w(f"  - {pid} {title}: {reason}")
        w(f"Skipped:              {len(others)}")
        for pid, title, _, reason in others:
            w(f"  - {pid} {title}: {reason}")
