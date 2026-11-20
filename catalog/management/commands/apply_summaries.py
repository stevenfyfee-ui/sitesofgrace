"""Replace summary_short on live site and trail pages from an approved JSON file.

    python manage.py apply_summaries short-summaries.json            # dry run: report only
    python manage.py apply_summaries short-summaries.json --commit   # save and publish

File: a list of entries, or {"pages": [...]}. Each entry has "title" (the page's exact
title), "summary_short" (the new text) and optionally "url_path_hint" (the page's public
path, e.g. /explore/marian-apparitions/rue-du-bac/; when set it must match too).

Each entry must match exactly one live SacredSitePage or PilgrimageTrailPage; zero or
several matches are reported and skipped, never guessed. Also skipped and reported: text
over 200 characters, a page with unpublished changes (a waiting draft is never published
by accident), a locked page, and a second entry for the same page.

--commit: sets summary_short on the live page, saves one revision (logged) and publishes
it, so every change is in the page's history and can be reverted from the admin. No other
field changes. Without --commit nothing is written.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import PilgrimageTrailPage, SacredSitePage

MAX_CHARS = 200
MODELS = (SacredSitePage, PilgrimageTrailPage)


def _norm_path(path):
    path = (path or "").strip()
    if path and not path.startswith("/"):
        path = "/" + path
    return path if not path or path.endswith("/") else path + "/"


def load_entries(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CommandError(f"Can't read {path}: {exc}")
    rows = data.get("pages") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise CommandError(f'{path}: expected a non-empty list of entries (or {{"pages": [...]}}).')
    return rows


def find_page(title, hint):
    matches = [p for model in MODELS for p in model.objects.live().filter(title=title)]
    if hint:
        want = _norm_path(hint)
        matches = [p for p in matches if want in (_norm_path(p.get_url()), _norm_path(p.url_path))]
    return matches


class Command(BaseCommand):
    help = "Replace summary_short on live site/trail pages from a JSON file (dry run unless --commit)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="The JSON file of approved summaries.")
        parser.add_argument("--commit", action="store_true", help="Save and publish. Without it, nothing is written.")

    def handle(self, *args, **options):
        commit = options["commit"]
        rows = load_entries(options["path"])
        mode = "COMMIT" if commit else "DRY RUN"
        self.stdout.write(f"{mode}: {options['path']} ({len(rows)} entries). "
                          + ("Each change is one published revision." if commit else "Nothing is written."))
        totals = {"changed": 0, "unchanged": 0, "skipped": 0}
        seen = set()
        for i, row in enumerate(rows, 1):
            outcome = self.entry(i, row, seen, commit)
            totals[outcome] += 1
        self.stdout.write(
            f"{'Changed and published' if commit else 'Would change'}: {totals['changed']}; "
            f"unchanged {totals['unchanged']}; skipped {totals['skipped']}."
        )

    def skip(self, i, label, reason):
        self.stdout.write(self.style.WARNING(f"[{i}] SKIPPED {label}: {reason}"))
        return "skipped"

    def entry(self, i, row, seen, commit):
        if not isinstance(row, dict):
            return self.skip(i, "?", "each entry must be an object")
        title, new, hint = row.get("title"), row.get("summary_short"), row.get("url_path_hint") or ""
        label = repr(title)
        if not isinstance(title, str) or not title or not isinstance(new, str) or not new.strip():
            return self.skip(i, label, 'needs "title" and a non-empty "summary_short"')
        matches = find_page(title, hint)
        if len(matches) != 1:
            where = f" at {hint}" if hint else ""
            found = "; ".join(f"#{p.pk} {p.get_url()}" for p in matches)
            return self.skip(i, label, f"{len(matches)} live site/trail page(s) titled exactly this{where}"
                                       + (f" ({found})" if found else "") + "; need exactly 1")
        page = matches[0]
        label = f"#{page.pk} {page.title!r} ({page.get_url()})"
        if page.pk in seen:
            return self.skip(i, label, "a second entry for the same page")
        seen.add(page.pk)
        if len(new) > MAX_CHARS:
            return self.skip(i, label, f"new text is {len(new)} characters (limit {MAX_CHARS})")
        if page.has_unpublished_changes:
            return self.skip(i, label, "the page has unpublished changes (a draft is waiting); publishing would release it")
        if page.locked:
            return self.skip(i, label, "the page is locked in the admin")
        old = page.summary_short or ""
        if old == new:
            self.stdout.write(f"[{i}] Unchanged {label}: already this text ({len(new)} chars)")
            return "unchanged"
        self.stdout.write(f"[{i}] {'Changed' if commit else 'Would change'} {label}: {len(old)} -> {len(new)} chars")
        self.stdout.write(f"      new: {new}")
        if commit:
            with transaction.atomic():
                page.summary_short = new
                revision = page.save_revision(log_action=True)
                revision.publish()
        return "changed"
