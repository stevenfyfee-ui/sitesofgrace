"""Import saint bodies, summaries (significance) and patronage onto existing
SaintPages from a JSON export.

    python manage.py import_saints tools/*saints_import*.json --dry-run
    python manage.py import_saints tools/*saints_import*.json
    python manage.py import_saints tools/*saints_import*.json --verify

<path> goes through glob.glob (the DO console mangles long pastes) and must
match exactly one file.

File shape: {"pages": [{slug, title, published, body_html, significance?,
patronage?, baseline_significance, baseline_patronage, baseline_body}]}.
An absent significance/patronage leaves that field alone; an empty string
clears it. Baselines are what each field held at export, normalized (see
normalize()).

Rules, per page:
  - Looked up by slug among the children of the saints index, and the title
    must match the file. Anything else is skipped and reported.
  - A field is safe to write when its current value (normalized) equals the
    baseline or already equals the new value. Anything else means someone
    edited the page after the export: a conflict, and the whole page is
    skipped. Accepting "already the new value" is what lets a second run
    report the page as already correct instead of as a conflict.
  - Live pages: one with unpublished changes is skipped (publishing would
    either lose the draft or publish it). Otherwise the fields are set and
    published through save_revision(log_action=True).publish() inside
    transaction.atomic().
  - Hidden pages are never published and live is never touched. Baselines
    are checked against the latest revision (the editor's view), falling
    back to the page row. Two things are written, in one transaction:
      * the page row's significance/patronage/body, because stub_saints
        decides "ready" with a queryset on the row's significance and
        publishes by flipping live on the row -- the row is what goes public;
      * a new draft revision built from the latest revision with the new
        fields applied (save_revision without publish), so the admin editor
        opens on the new content and keeps any other draft edits.
    Each half is written only when it differs, so a rerun creates nothing.
  - Everything is validated before anything is written: the target fields
    must exist on SaintPage, values must be strings, and body_html must
    parse as balanced HTML using tags the body's rich text editor supports.

--dry-run runs the same reading, validation and comparison and prints the
same report, writing nothing. --verify writes nothing and checks every page
in the file against it field by field (normalized); for live pages it also
confirms the latest revision is the live one.
"""
import glob
import html
import json
import re
from collections import Counter
from html.parser import HTMLParser

from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Page

from catalog.management.commands.import_catalog import SAINTS_PARENT_SLUG
from catalog.models import SaintPage

# file key -> SaintPage field
FIELDS = {"significance": "significance", "patronage": "patronage", "body_html": "body"}
BASELINES = {"significance": "baseline_significance", "patronage": "baseline_patronage",
             "body": "baseline_body"}

# Tags the default Draftail features (SaintPage.body sets none of its own)
# store. Anything else would be dropped the first time an editor saves.
ALLOWED_TAGS = {"p", "h2", "h3", "h4", "b", "strong", "i", "em", "a", "ul", "ol", "li", "br", "hr"}
VOID_TAGS = {"br", "hr"}

_TAG_RE = re.compile(r"<[^>]*>")
_KEEP_RE = re.compile(r"[^a-z0-9]")


def normalize(value):
    """Strip tags, unescape entities, lowercase, keep only [a-z0-9]. Every
    baseline comparison goes through this."""
    text = html.unescape(_TAG_RE.sub("", value or ""))
    return _KEEP_RE.sub("", text.lower())


class _BalanceChecker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"unsupported tag <{tag}>")
        elif tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"unsupported tag <{tag}/>")

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}>")
        else:
            self.stack.pop()


def html_problem(value):
    """None if value is balanced HTML using allowed tags, else the reason."""
    checker = _BalanceChecker()
    try:
        checker.feed(value)
        checker.close()
    except Exception as exc:  # HTMLParser is lenient; this is belt and braces
        return f"does not parse: {exc}"
    if checker.errors:
        return checker.errors[0]
    if checker.stack:
        return f"unclosed <{checker.stack[-1]}>"
    return None


class SkipPage(Exception):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category  # "skipped" or "conflict"
        self.reason = reason


class Command(BaseCommand):
    help = "Import saint bodies, summaries and patronage from a JSON file."

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

    def _saints_index(self):
        matches = list(Page.objects.filter(slug=SAINTS_PARENT_SLUG))
        if len(matches) != 1:
            raise CommandError(
                f"expected exactly one page with slug {SAINTS_PARENT_SLUG!r}; found {len(matches)}"
            )
        return matches[0]

    # ------------------------------------------------------------- validation

    def _validate(self, entry):
        for key, field in FIELDS.items():
            try:
                SaintPage._meta.get_field(field)
            except FieldDoesNotExist:
                raise SkipPage("skipped", f"SaintPage has no field {field!r}")
            if key in entry and not isinstance(entry[key], str):
                raise SkipPage("skipped", f"{key} is not a string")
        if not entry.get("body_html"):
            raise SkipPage("skipped", "body_html is missing or empty")
        for field, key in BASELINES.items():
            if not isinstance(entry.get(key), str):
                raise SkipPage("skipped", f"{key} is missing or not a string")
        problem = html_problem(entry["body_html"])
        if problem:
            raise SkipPage("skipped", f"body_html: {problem}")

    def _lookup(self, entry, index):
        found = list(SaintPage.objects.child_of(index).filter(slug=entry.get("slug")))
        if len(found) != 1:
            raise SkipPage("skipped", f"{len(found)} saint pages with this slug under the saints index")
        page = found[0]
        if page.title != entry.get("title"):
            raise SkipPage("skipped", f"title mismatch: database has {page.title!r}")
        if page.live and page.has_unpublished_changes:
            raise SkipPage("skipped", "page has unpublished changes (draft)")
        return page

    # ------------------------------------------------------------------- plan

    @staticmethod
    def _targets(entry):
        """SaintPage field -> new value, for the fields this entry sets."""
        return {field: entry[key] for key, field in FIELDS.items() if key in entry}

    @staticmethod
    def _differs(obj, targets):
        return {f: v for f, v in targets.items() if getattr(obj, f) != v}

    def _check_baselines(self, obj, entry, targets):
        """A field is fine if it still matches its baseline or already holds
        the new value. Anything else was edited after the export."""
        edited = []
        for field, key in BASELINES.items():
            current = normalize(getattr(obj, field))
            if current == normalize(entry[key]):
                continue
            if field in targets and current == normalize(targets[field]):
                continue
            edited.append(field)
        if edited:
            raise SkipPage("conflict", f"edited since export: {', '.join(edited)}")

    def _plan(self, entry, page):
        targets = self._targets(entry)
        if page.live:
            self._check_baselines(page, entry, targets)
            return {"row": self._differs(page, targets), "revision_obj": None, "revision": {}}
        draft = page.get_latest_revision_as_object() or page
        self._check_baselines(draft, entry, targets)
        return {"row": self._differs(page, targets), "revision_obj": draft,
                "revision": self._differs(draft, targets)}

    def _apply(self, page, plan):
        with transaction.atomic():
            if page.live:
                for field, value in plan["row"].items():
                    setattr(page, field, value)
                page.save_revision(log_action=True).publish()
                return
            # Hidden: never publish, never touch live.
            if plan["row"]:
                for field, value in plan["row"].items():
                    setattr(page, field, value)
                page.save(update_fields=list(plan["row"]))
            if plan["revision"]:
                draft = plan["revision_obj"]
                for field, value in plan["revision"].items():
                    setattr(draft, field, value)
                # save_revision only writes revision bookkeeping columns to
                # the row (latest_revision, draft_title, ...), not content.
                draft.save_revision(log_action=True)

    # ---------------------------------------------------------------- verify

    def _verify(self, path, entries, index):
        matched, mismatched = 0, []
        for entry in entries:
            found = list(SaintPage.objects.child_of(index).filter(slug=entry.get("slug")))
            problems = []
            if len(found) != 1:
                problems.append(f"{len(found)} pages with this slug")
            else:
                page = found[0]
                if page.title != entry.get("title"):
                    problems.append("title differs")
                targets = self._targets(entry)
                problems += [f for f, v in targets.items() if normalize(getattr(page, f)) != normalize(v)]
                if page.live:
                    if page.has_unpublished_changes or page.live_revision_id != page.latest_revision_id:
                        problems.append("latest revision is not the live one")
                else:
                    draft = page.get_latest_revision_as_object() or page
                    problems += [f"draft {f}" for f, v in targets.items()
                                 if normalize(getattr(draft, f)) != normalize(v)]
            if problems:
                mismatched.append((entry.get("slug"), entry.get("title"), problems))
            else:
                matched += 1

        w = self.stdout.write
        w(f"Verify {path}")
        w(f"  Pages in file:                 {len(entries)}")
        w(f"  Pages matching the file:       {matched}")
        w(f"  Pages NOT matching:            {len(mismatched)}")
        for slug, title, problems in mismatched:
            w(f"    - {slug} {title}: {', '.join(problems)}")
        if mismatched:
            raise CommandError(f"{len(mismatched)} page(s) do not match the file.")

    # ------------------------------------------------------------------ main

    def handle(self, *args, **options):
        path, entries = self._load(options["path"])
        index = self._saints_index()

        if options["verify"]:
            return self._verify(path, entries, index)

        dry_run = options["dry_run"]
        totals = Counter()
        skipped = []  # (slug, title, category, reason)

        w = self.stdout.write
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Importing {path}")
        for entry in entries:
            try:
                self._validate(entry)
                page = self._lookup(entry, index)
                plan = self._plan(entry, page)
            except SkipPage as skip:
                skipped.append((entry.get("slug"), entry.get("title"), skip.category, skip.reason))
                continue

            changed = set(plan["row"]) | set(plan["revision"])
            if not changed:
                totals["already_correct"] += 1
                continue
            if not dry_run:
                self._apply(page, plan)
            state = "published" if page.live else "hidden"
            totals["changed"] += 1
            totals[f"{state}_body"] += "body" in changed
            totals["significance"] += "significance" in changed
            totals["patronage"] += "patronage" in changed
            note = ""
            if bool(entry.get("published")) != page.live:
                note = f" (file says {'published' if entry.get('published') else 'hidden'})"
            w(f"  {'would change' if dry_run else 'changed'} [{state}] {page.slug} "
              f"{page.title}: {', '.join(sorted(changed))}{note}")

        conflicts = [s for s in skipped if s[2] == "conflict"]
        others = [s for s in skipped if s[2] != "conflict"]
        w("")
        w(f"{'Would change' if dry_run else 'Pages changed'}:          {totals['changed']}")
        w(f"Published bodies updated:  {totals['published_body']}")
        w(f"Hidden bodies updated:     {totals['hidden_body']}")
        w(f"Summaries set:             {totals['significance']}")
        w(f"Patronages set:            {totals['patronage']}")
        w(f"Already correct:           {totals['already_correct']}")
        w(f"Conflicts:                 {len(conflicts)}")
        for slug, title, _, reason in conflicts:
            w(f"  - {slug} {title}: {reason}")
        w(f"Skipped:                   {len(others)}")
        for slug, title, _, reason in others:
            w(f"  - {slug} {title}: {reason}")
