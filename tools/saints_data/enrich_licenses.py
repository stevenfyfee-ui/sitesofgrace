#!/usr/bin/env python3
"""Add an image_license column to enrichment.csv by looking up each image's
Commons file-page license via the Commons API (extmetadata).

Read-only against Commons; reuses wikidata_saints' http_json cache/backoff.

    python enrich_licenses.py
"""
import csv
import hashlib
import html
import os
import re
import sys
from urllib.parse import unquote, urlencode

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wikidata_saints as w

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "enrichment.csv")

COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def filename_from(image_url: str) -> str:
    path = image_url.split("?", 1)[0]
    return unquote(path.rsplit("/", 1)[-1])


def plain_text(value: str) -> str:
    """Commons extmetadata fields carry raw HTML: <a> links, or plain text
    followed by a hidden <span> repeating the same text (e.g. "Unknown
    author<span style='display:none'>Unknown author</span>") for screen
    readers. Stripping tags alone would double that text up, so prefer
    whatever precedes the first tag and only fall back to full stripping
    when there isn't any (the <a>-link case)."""
    if not value:
        return ""
    before_tag = value.split("<", 1)[0].strip()
    if before_tag:
        return html.unescape(before_tag)
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def classify(extmeta: dict) -> tuple[str, str]:
    """Returns (license, credit). credit is only non-empty when the licence
    requires attribution — public domain and CC0 need none."""
    if not extmeta:
        return "unknown", ""
    license_name = (extmeta.get("LicenseShortName", {}).get("value") or "").strip()
    copyrighted = (extmeta.get("Copyrighted", {}).get("value") or "").strip().lower()
    usage = (extmeta.get("UsageTerms", {}).get("value") or "").strip()
    text = f"{license_name} {usage}".lower()
    if copyrighted == "false" or "public domain" in text or "cc0" in text or "pd-" in text:
        return "public domain", ""
    if license_name:
        artist = plain_text(extmeta.get("Artist", {}).get("value", "")) or "Unknown author"
        credit = f"{artist} — Wikimedia Commons, {license_name}"
        return f"needs review: {license_name}", credit[:255]
    return "unknown", ""


def lookup(filename: str) -> tuple[str, str]:
    key = "lic_" + hashlib.sha1(filename.encode("utf8")).hexdigest()[:16]
    api_url = COMMONS_API + "?" + urlencode({
        "action": "query", "titles": "File:" + filename, "prop": "imageinfo",
        "iiprop": "extmetadata", "format": "json"})
    try:
        payload = w.http_json(api_url, key)
    except RuntimeError as exc:
        print(f"  !! license lookup failed for {filename!r}: {exc}", file=sys.stderr)
        return "unknown", ""
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            return "unknown", ""
        info = page.get("imageinfo")
        if info:
            return classify(info[0].get("extmetadata", {}))
    return "unknown", ""


def main() -> None:
    with open(PATH, encoding="utf8") as fh:
        rows = list(csv.DictReader(fh))
        fields = fh and list(rows[0].keys()) if rows else []

    cache: dict[str, tuple[str, str]] = {}
    for i, row in enumerate(rows):
        url = row.get("image_url", "")
        if not url:
            row["image_license"], row["image_credit"] = "", ""
            continue
        fname = filename_from(url)
        if fname not in cache:
            print(f"  license {i + 1}/{len(rows)}: {fname}")
            cache[fname] = lookup(fname)
        row["image_license"], row["image_credit"] = cache[fname]

    out_fields = list(fields)
    for extra in ("image_license", "image_credit"):
        if extra not in out_fields:
            out_fields.append(extra)
    with open(PATH, "w", newline="", encoding="utf8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {PATH} ({len(rows)} rows, {len(cache)} unique images looked up)")


if __name__ == "__main__":
    main()
