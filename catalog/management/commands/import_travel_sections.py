"""Import "Plan Your Visit" travel sections, Quick Card fields and feast days
onto existing SacredSitePages from a JSON export.

    python manage.py import_travel_sections tools/*travel_import*.json --dry-run
    python manage.py import_travel_sections tools/*travel_import*.json
    python manage.py import_travel_sections tools/*travel_import*.json --verify

<path> goes through glob.glob (the DO console mangles long pastes) and must
match exactly one file.

File shape: {"pages": [{id, title, url, feast_day?, quick?, sections?}]},
each section {kind, action: "create"|"update", teaser?, body_html?}. A key
that is absent leaves that value alone.

Rules, per page:
  - Looked up by id only, never by slug or title. A missing id or a title
    that doesn't match the file is skipped and reported.
  - A page with unpublished changes is skipped: publishing on top of a draft
    would either lose the draft or publish it. A page that isn't live is
    skipped too: publishing would make it public.
  - Everything is validated before anything is written; one bad value skips
    the whole page. Lengths come from each field's max_length, never from a
    number in this file. Quick keys must be real quick_* fields on the page.
  - create: adds the section if its kind is missing; an identical existing
    section counts as already correct; a DIFFERENT existing one is a
    conflict, and a conflict skips the whole page rather than leaving it
    half-imported.
  - update: the section must already exist; body/teaser are set only when
    present and different.
  - A page that changed is published through save_revision(log_action=True)
    .publish() inside transaction.atomic(), so the new revision carries the
    sections. A page with nothing to change gets no revision, which is what
    makes a second run report 0 changed.

--dry-run runs the same reading and validation and prints the same report,
writing nothing. --verify writes nothing and checks the database against the
file value by value -- the proof the import ran, not just that it was quiet.
"""
import glob
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SacredSitePage, SiteTravelSection
from catalog.travel_sections import TRAVEL_ORDER, TRAVEL_SECTION_CHOICES

VALID_KINDS = {key for key, _ in TRAVEL_SECTION_CHOICES}
VALID_ACTIONS = {"create", "update"}
FULL_SECTION_COUNT = len(TRAVEL_SECTION_CHOICES)


def _max_length(model, field_name):
    return model._meta.get_field(field_name).max_length


def _quick_fields():
    """Concrete quick_* fields on SacredSitePage, name -> max_length."""
    return {
        f.name: f.max_length
        for f in SacredSitePage._meta.concrete_fields
        if f.name.startswith("quick_")
    }


class SkipPage(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category  # "skipped" or "conflict"
        self.reason = reason


class Command(BaseCommand):
    help = "Import travel sections, Quick Card fields and feast days from a JSON file."

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

    # ------------------------------------------------------------- validation

    def _validate(self, entry, page):
        """Raises SkipPage on anything invalid. Returns nothing -- the plan is
        built separately once the whole entry is known to be clean."""
        if "feast_day" in entry:
            value = entry["feast_day"]
            limit = _max_length(SacredSitePage, "feast_day")
            if not isinstance(value, str):
                raise SkipPage("skipped", "feast_day is not a string")
            if len(value) > limit:
                raise SkipPage("skipped", f"feast_day is {len(value)} chars (max {limit})")

        quick = entry.get("quick", {})
        if not isinstance(quick, dict):
            raise SkipPage("skipped", "quick is not an object")
        quick_fields = _quick_fields()
        for name, value in quick.items():
            if name not in quick_fields:
                raise SkipPage("skipped", f"quick field {name!r} does not exist")
            if not isinstance(value, str):
                raise SkipPage("skipped", f"{name} is not a string")
            if len(value) > quick_fields[name]:
                raise SkipPage("skipped", f"{name} is {len(value)} chars (max {quick_fields[name]})")

        sections = entry.get("sections", [])
        if not isinstance(sections, list):
            raise SkipPage("skipped", "sections is not a list")
        teaser_limit = _max_length(SiteTravelSection, "teaser")
        seen = set()
        for section in sections:
            kind = section.get("kind")
            if kind not in VALID_KINDS:
                raise SkipPage("skipped", f"unknown section kind {kind!r}")
            if kind in seen:
                raise SkipPage("skipped", f"section {kind} appears twice")
            seen.add(kind)
            if section.get("action") not in VALID_ACTIONS:
                raise SkipPage("skipped", f"{kind}: unknown action {section.get('action')!r}")
            for key in ("teaser", "body_html"):
                if key in section and not isinstance(section[key], str):
                    raise SkipPage("skipped", f"{kind}: {key} is not a string")
            if "teaser" in section and len(section["teaser"]) > teaser_limit:
                raise SkipPage(
                    "skipped", f"{kind}: teaser is {len(section['teaser'])} chars (max {teaser_limit})"
                )
            if section["action"] == "create" and not section.get("body_html"):
                raise SkipPage("skipped", f"{kind}: create without body_html")

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

    # ------------------------------------------------------------------- plan

    def _plan(self, entry, page, existing):
        """What would change, as plain data. `existing` is kind -> section.
        Raises SkipPage("conflict") for a create against a different body."""
        plan = {"fields": {}, "create": [], "update": [], "already_correct": 0,
                "bodies": 0, "teasers": 0, "quick": 0, "feast": 0}

        if "feast_day" in entry and page.feast_day != entry["feast_day"]:
            plan["fields"]["feast_day"] = entry["feast_day"]
            plan["feast"] += 1
        for name, value in entry.get("quick", {}).items():
            if getattr(page, name) != value:
                plan["fields"][name] = value
                plan["quick"] += 1

        for section in entry.get("sections", []):
            kind, current = section["kind"], existing.get(section["kind"])
            if section["action"] == "create":
                if current is None:
                    plan["create"].append(section)
                    continue
                same_body = current.body == section["body_html"]
                same_teaser = "teaser" not in section or current.teaser == section["teaser"]
                if same_body and same_teaser:
                    plan["already_correct"] += 1
                    continue
                raise SkipPage("conflict", f"{kind}: create, but a different section already exists")
            # update
            if current is None:
                raise SkipPage("skipped", f"{kind}: update, but the section does not exist")
            changes = {}
            if "body_html" in section and current.body != section["body_html"]:
                changes["body"] = section["body_html"]
                plan["bodies"] += 1
            if "teaser" in section and current.teaser != section["teaser"]:
                changes["teaser"] = section["teaser"]
                plan["teasers"] += 1
            if changes:
                plan["update"].append((kind, changes))
            else:
                plan["already_correct"] += 1
        return plan

    @staticmethod
    def _has_changes(plan):
        return bool(plan["fields"] or plan["create"] or plan["update"])

    def _apply(self, page, plan):
        with transaction.atomic():
            for name, value in plan["fields"].items():
                setattr(page, name, value)
            # Work through the in-memory ParentalKey relation so the revision
            # serializes the full set of sections and publish() commits them
            # -- the (page, kind) unique constraint holds because each kind is
            # either updated in place or created only when absent.
            sections = list(page.travel_sections.all())
            by_kind = {s.kind: s for s in sections}
            for kind, changes in plan["update"]:
                for attr, value in changes.items():
                    setattr(by_kind[kind], attr, value)
            for section in plan["create"]:
                sections.append(SiteTravelSection(
                    kind=section["kind"],
                    teaser=section.get("teaser", ""),
                    body=section["body_html"],
                    sort_order=TRAVEL_ORDER[section["kind"]],
                ))
            page.travel_sections = sections
            page.save_revision(log_action=True).publish()

    # ---------------------------------------------------------------- verify

    def _verify(self, path, entries, pages_by_id):
        matched, mismatched = 0, []
        sections_by_page = {}
        for s in SiteTravelSection.objects.filter(page_id__in=pages_by_id.keys()):
            sections_by_page.setdefault(s.page_id, {})[s.kind] = s
        for entry in entries:
            page = pages_by_id.get(entry.get("id"))
            problems = []
            if page is None:
                problems.append("page not found")
            else:
                if page.title != entry.get("title"):
                    problems.append("title differs")
                if "feast_day" in entry and page.feast_day != entry["feast_day"]:
                    problems.append("feast_day")
                for name, value in entry.get("quick", {}).items():
                    if getattr(page, name, None) != value:
                        problems.append(name)
                existing = sections_by_page.get(page.pk, {})
                for section in entry.get("sections", []):
                    current = existing.get(section["kind"])
                    if current is None:
                        problems.append(f"{section['kind']} missing")
                        continue
                    if "body_html" in section and current.body != section["body_html"]:
                        problems.append(f"{section['kind']} body")
                    if "teaser" in section and current.teaser != section["teaser"]:
                        problems.append(f"{section['kind']} teaser")
            if problems:
                mismatched.append((entry.get("id"), entry.get("title"), problems))
            else:
                matched += 1

        counts = Counter(SiteTravelSection.objects.values_list("page_id", flat=True))
        all_pages = SacredSitePage.objects.count()
        full = sum(1 for pk in SacredSitePage.objects.values_list("pk", flat=True)
                   if counts.get(pk, 0) == FULL_SECTION_COUNT)

        w = self.stdout.write
        w(f"Verify {path}")
        w(f"  Pages in file:                 {len(entries)}")
        w(f"  Pages matching the file:       {matched}")
        w(f"  Pages NOT matching:            {len(mismatched)}")
        for pid, title, problems in mismatched:
            shown = ", ".join(problems[:6]) + (f" (+{len(problems) - 6} more)" if len(problems) > 6 else "")
            w(f"    - {pid} {title}: {shown}")
        w(f"  Site pages with {FULL_SECTION_COUNT} travel sections: {full} of {all_pages}")
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
        sections_by_page = {}
        for s in SiteTravelSection.objects.filter(page_id__in=pages_by_id.keys()):
            sections_by_page.setdefault(s.page_id, {})[s.kind] = s

        w = self.stdout.write
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Importing {path}")
        for entry in entries:
            try:
                page = self._lookup(entry, pages_by_id)
                self._validate(entry, page)
                plan = self._plan(entry, page, sections_by_page.get(page.pk, {}))
            except SkipPage as skip:
                skipped.append((entry.get("id"), entry.get("title"), skip.category, skip.reason))
                continue

            totals["already_correct"] += plan["already_correct"]
            if not self._has_changes(plan):
                totals["unchanged"] += 1
                continue
            if not dry_run:
                self._apply(page, plan)
            totals["changed"] += 1
            totals["created"] += len(plan["create"])
            totals["bodies"] += plan["bodies"]
            totals["teasers"] += plan["teasers"]
            totals["quick"] += plan["quick"]
            totals["feast"] += plan["feast"]
            w(
                f"  {'would change' if dry_run else 'changed'} {page.pk} {page.title}: "
                f"+{len(plan['create'])} sections, {plan['bodies']} bodies, {plan['teasers']} teasers, "
                f"{plan['quick']} quick, {plan['feast']} feast day"
            )

        conflicts = [s for s in skipped if s[2] == "conflict"]
        others = [s for s in skipped if s[2] != "conflict"]
        w("")
        w(f"{'Would change' if dry_run else 'Pages changed'}:  {totals['changed']}")
        w(f"Pages unchanged:      {totals['unchanged']}")
        w(f"Sections created:     {totals['created']}")
        w(f"Bodies updated:       {totals['bodies']}")
        w(f"Teasers updated:      {totals['teasers']}")
        w(f"Quick Card fields set: {totals['quick']}")
        w(f"Feast days set:       {totals['feast']}")
        w(f"Already correct:      {totals['already_correct']}")
        w(f"Conflicts:            {len(conflicts)}")
        for pid, title, _, reason in conflicts:
            w(f"  - {pid} {title}: {reason}")
        w(f"Skipped:              {len(others)}")
        for pid, title, _, reason in others:
            w(f"  - {pid} {title}: {reason}")
