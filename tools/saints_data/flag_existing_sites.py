#!/usr/bin/env python3
"""Add an existing_site_match column to candidates.csv: does the candidate's
burial place look like one of our 217 sacred sites already?

Fuzzy on purpose (this flags possible duplicates for a human to check, it
does not decide anything) — better to over-flag than let a real duplicate
pin through.

    python flag_existing_sites.py
"""
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wikidata_saints as w

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CAND_PATH = os.path.join(HERE, "candidates.csv")
EXPORT_PATH = os.path.join(REPO, "tools", "catalog_export.json")

# Generic Catholic devotional/architectural vocabulary that recurs across
# hundreds of unrelated buildings ("Church of the Immaculate Conception",
# "Basilica of Our Lady of Sorrows") and would otherwise look like a distinctive
# match on its own. Stripped before comparing.
STOPWORDS = {
    "the", "of", "and", "de", "la", "le", "du", "in", "at", "san", "santa",
    "sant", "saint", "saints", "st", "sts", "basilica", "basilique",
    "cathedral", "church", "chiesa", "iglesia", "kirche", "chapel",
    "chapelle", "abbey", "abbaye", "shrine", "sanctuary", "tomb", "relics",
    "monastery", "convent", "mission", "parish", "mary", "maria", "marie",
    "jesus", "lady", "our", "notre", "dame", "holy", "sacred", "heart",
    "immaculate", "conception", "divine", "mercy", "blessed", "virgin",
    "national", "co", "cemetery", "memorial", "crypt", "vault", "royal",
    "great", "major", "minor", "mount", "house", "provincial", "nuestra",
    "senora", "padre", "madre", "santi", "santo", "nossa", "senhora",
    "igreja", "metropolitan", "first",
}


def tokens(text: str) -> set[str]:
    return {t for t in w.fold(text).split() if len(t) >= 4 and t not in STOPWORDS}


def main() -> None:
    export = json.load(open(EXPORT_PATH, encoding="utf8"))
    sites = []
    for s in export["sites"]:
        main_name = re.sub(r"\s*\([^)]*\)\s*$", "", s["title"])
        sites.append({
            "title": s["title"],
            "name_folded": w.fold(main_name),
            "name_tokens": tokens(main_name),
            "locality_folded": w.fold(s.get("locality", "")),
        })

    with open(CAND_PATH, encoding="utf8") as fh:
        rows = list(csv.DictReader(fh))
    fields = list(rows[0].keys()) if rows else []

    matched = 0
    for row in rows:
        burial = row.get("burial", "")
        row["existing_site_match"] = ""
        if not burial:
            continue
        b_folded = w.fold(burial)
        b_tokens = tokens(burial)
        best_title, best_score = None, 0.0
        for site in sites:
            score = 0.0
            # Tier A: the whole place name matches once generic words are
            # gone either way, this is almost certainly the same building.
            if b_folded and site["name_folded"] and b_folded == site["name_folded"]:
                score = 1.0
            # Tier B: at least two distinctive words in common — a single
            # shared word is too easy to hit by coincidence (e.g. a shared
            # city name), so this requires two independent ones to agree.
            elif (len(b_tokens) >= 2 and site["name_tokens"]
                  and b_tokens.issubset(site["name_tokens"])):
                score = 0.9
            # Tier C: burial place is just a town/city name, and it equals
            # this site's locality exactly. Weaker — same town, not
            # necessarily the same building — kept as a lower-confidence flag.
            elif (b_folded and site["locality_folded"]
                  and b_folded == site["locality_folded"] and len(b_folded) >= 5):
                score = 0.7
            if score > best_score:
                best_title, best_score = site["title"], score
        if best_title and best_score >= 0.7:
            row["existing_site_match"] = best_title
            matched += 1

    out_fields = fields + ["existing_site_match"] if "existing_site_match" not in fields else fields
    with open(CAND_PATH, "w", newline="", encoding="utf8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {CAND_PATH} ({len(rows)} rows, {matched} flagged as possible existing-site matches)")


if __name__ == "__main__":
    main()
