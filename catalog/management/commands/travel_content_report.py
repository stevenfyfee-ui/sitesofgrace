"""Flag near-identical "Plan Your Visit" text across sites -- a rewrite worklist.

    python manage.py travel_content_report --out travel_report.csv
    python manage.py travel_content_report --out travel_report.csv --threshold 0.7
    python manage.py travel_content_report --out travel_report.csv --all
    python manage.py travel_content_report --out - --all     # print the CSV to the console

Read-only: it reads SiteTravelSection bodies and writes a CSV; nothing in
the database changes.

Method. Each body is reduced to plain text, lowercased, and has the page's
own names masked -- its title, locality, country and principal saint (each
phrase, and each of their words of four or more letters) become "<name>",
every number becomes "#". What is left is the text a template would share.
Bodies are then compared within the same section kind using the Jaccard
similarity of their word 3-gram shingles (|A ∩ B| / |A ∪ B|, 0 to 1): 1.0
means the same sentences in the same order apart from the masked names.
Each page gets the score of its closest match. Rows at or above --threshold
(default 0.8) are written; --all writes every page.

Columns: page id, title, url, kind, similarity, closest match (id and title).
"""
import csv
import re

from django.core.management.base import BaseCommand
from django.utils.html import strip_tags

from catalog.management.csv_output import csv_destination, describe, summary
from catalog.models import SiteTravelSection
from catalog.travel_sections import TRAVEL_SECTION_CHOICES

SHINGLE = 3
MIN_WORD = 4
_WORD_RE = re.compile(r"[a-z0-9<>#']+")
_NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*")


def page_names(page):
    phrases = [page.title, page.locality, page.country]
    if page.associated_saint_id:
        phrases.append(page.associated_saint.title)
    phrases = [p.strip().lower() for p in phrases if p and p.strip()]
    words = {w for p in phrases for w in re.findall(r"[a-z']+", p) if len(w) >= MIN_WORD}
    # Longest first, so "our lady of lourdes" is masked before "lourdes".
    return sorted(set(phrases) | words, key=len, reverse=True)


def masked_tokens(html, names):
    text = " ".join(strip_tags(html or "").lower().split())
    for name in names:
        text = re.sub(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", " <name> ", text)
    text = _NUMBER_RE.sub(" # ", text)
    return _WORD_RE.findall(text)


def shingles(tokens):
    if len(tokens) < SHINGLE:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + SHINGLE]) for i in range(len(tokens) - SHINGLE + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Command(BaseCommand):
    help = "CSV of travel sections whose text is near-identical to another site's (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help='Path of the CSV to write; "-" prints it to the console.')
        parser.add_argument("--threshold", type=float, default=0.8,
                            help="Minimum similarity to report (default 0.8).")
        parser.add_argument("--all", action="store_true", help="Write every page, not only flagged ones.")

    def handle(self, *args, **options):
        threshold = options["threshold"]
        sections = (
            SiteTravelSection.objects.select_related("page", "page__associated_saint")
            .order_by("kind", "page__title")
        )
        by_kind = {}
        for section in sections:
            page = section.page
            by_kind.setdefault(section.kind, []).append(
                (page, shingles(masked_tokens(section.body, page_names(page))))
            )

        rows, flagged = [], 0
        for kind, _label in TRAVEL_SECTION_CHOICES:
            entries = by_kind.get(kind, [])
            for i, (page, sh) in enumerate(entries):
                best, match = 0.0, None
                for j, (other, other_sh) in enumerate(entries):
                    if i == j:
                        continue
                    score = jaccard(sh, other_sh)
                    if score > best:
                        best, match = score, other
                if best >= threshold:
                    flagged += 1
                if best >= threshold or options["all"]:
                    rows.append([
                        page.pk, page.title, page.full_url or page.url_path, kind, f"{best:.3f}",
                        f"{match.pk} {match.title}" if match else "",
                    ])

        rows.sort(key=lambda r: (r[3], -float(r[4]), r[1]))
        with csv_destination(options["out"], self) as fh:
            writer = csv.writer(fh)
            writer.writerow(["page_id", "title", "url", "kind", "similarity", "closest_match"])
            writer.writerows(rows)
        total = sum(len(v) for v in by_kind.values())
        summary(
            self, options["out"],
            f"compared {total} sections in {len(by_kind)} kinds; {flagged} at or above {threshold} "
            f"(word {SHINGLE}-gram Jaccard after masking names and numbers); wrote {len(rows)} rows "
            f"to {describe(options['out'])}"
        )
