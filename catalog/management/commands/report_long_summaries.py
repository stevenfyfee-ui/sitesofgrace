"""List the live pages whose directory-card text is longer than a card shows -- an editing worklist.

    python manage.py report_long_summaries
    python manage.py report_long_summaries --limit 160

Read-only: nothing in the database changes, and no text is rewritten or cut.

Checked: SacredSitePage and PilgrimageTrailPage summary_short, and SaintPage
significance (the text on the directory cards, map popups and search results).
Rows over --limit characters (default 200), longest first: characters, type,
title, URL path and the admin edit URL.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from catalog.models import PilgrimageTrailPage, SacredSitePage, SaintPage

SOURCES = (
    (SacredSitePage, "summary_short", "Site"),
    (PilgrimageTrailPage, "summary_short", "Trail"),
    (SaintPage, "significance", "Saint"),
)


def admin_edit_url(page):
    path = reverse("wagtailadmin_pages:edit", args=[page.pk])
    base = (getattr(settings, "WAGTAILADMIN_BASE_URL", "") or "").rstrip("/")
    # The base.py placeholder isn't a real address; a path is more useful than a wrong host.
    return path if not base or "example.com" in base else base + path


def long_summaries(limit):
    rows = []
    for model, field, kind in SOURCES:
        for page in model.objects.live().only("id", "title", "url_path", field):
            text = getattr(page, field) or ""
            if len(text) > limit:
                rows.append({"chars": len(text), "kind": kind, "field": field, "title": page.title,
                             "path": page.get_url() or page.url_path, "admin": admin_edit_url(page)})
    rows.sort(key=lambda r: (-r["chars"], r["title"]))
    return rows


class Command(BaseCommand):
    help = "List live sites, trails and saints whose card text is over --limit characters (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Report text longer than this (default 200).")

    def handle(self, *args, **options):
        limit = options["limit"]
        rows = long_summaries(limit)
        self.stdout.write(f"{len(rows)} live page(s) with card text over {limit} characters (longest first). "
                          f"Read-only; nothing was changed.")
        for r in rows:
            self.stdout.write(f"{r['chars']:>5}  {r['kind']:<5}  {r['title']}  ({r['field']})")
            self.stdout.write(f"       {r['path']}")
            self.stdout.write(f"       {r['admin']}")
