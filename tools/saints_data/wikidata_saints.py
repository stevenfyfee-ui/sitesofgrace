#!/usr/bin/env python3
"""Harvest saint facts from Wikidata for Sites of Grace.  (v2)

Wikidata is CC0 — no attribution required. This takes ONLY facts (dates,
places, coordinates, orders, identifiers). It never copies prose.

WHY v2: v1 downloaded every saint Wikidata knows (~15k) and filtered locally.
That was wrong. Deep LIMIT/OFFSET pagination times out, it depends on getting
canonization-status QIDs exactly right (v1 did not — Q41304 is the Weimar
Republic, not "blessed"), and one bad constant silently drops most of the
universe. We already know our 500 names, so v2 asks about those names directly:
small queries against the label index, each independently retryable.

    python wikidata_saints.py --probe     # match + coverage report. RUN FIRST.
    python wikidata_saints.py --enrich    # full field pull for matches
    python wikidata_saints.py --expand    # find saints we do not have

Every query is cached under cache/ keyed by a hash of the query text, so
re-running is cheap and a changed query never reads a stale answer.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(HERE, "cache")

ENDPOINT = "https://query.wikidata.org/sparql"
SEARCH_API = "https://www.wikidata.org/w/api.php"
UA = "SitesOfGrace-saints/2.0 (https://sitesofgrace.com; stevenf@eoshost.com)"

# Properties. Verified by Claude Code on 2026-09-22 against Anthony of Padua
# and Francis of Assisi.
P_FEAST = "P841"
P_BIRTH = "P569"
P_DEATH = "P570"
P_BURIAL = "P119"
P_COORD = "P625"
P_ORDER = "P611"          # religious order — verified
P_PATRONAGE = "P2925"     # domain of saint or deity — verified
P_IMAGE = "P18"
P_STATUS = "P411"         # canonization status
P_COMMONS = "P373"
P_INSTANCE = "P31"

# Classes a saint may be an instance of. Q20643955 ("human biblical figure")
# is how Wikidata tags apostles and Old/New Testament people — without it,
# Joseph, Andrew and Jude fall out.
CLASSES = ["wd:Q5", "wd:Q20643955"]


# --------------------------------------------------------------------- utils

def fold(name: str) -> str:
    """Normalise for comparison. Mirrors link_site_saints.py."""
    text = (name or "").strip()
    for a, b in {"æ": "ae", "Æ": "AE", "œ": "oe", "ø": "o", "ł": "l"}.items():
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^A-Za-z0-9 ]", " ", text)
    text = re.sub(r"\b(sts?|saints?|blessed|bl|pope|the|of|and)\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip().lower()


def search_names(title: str) -> list[str]:
    """Candidate Wikidata labels for one of our page titles.

    Our titles carry honorifics and parentheticals that Wikidata labels do not:
    "St. Therese of Lisieux (Little Flower of Jesus)" -> "Therese of Lisieux".
    Accents are KEPT — Wikidata labels have them.
    """
    base = re.sub(r"\([^)]*\)", " ", title)
    # Repeat: "Pope St. John Paul II" needs two passes, not one.
    prev = None
    while prev != base:
        prev = base
        base = re.sub(r"^\s*(Sts?\.|Saints?|Blessed|Bl\.|Pope)\s+", "", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip(" ,;")
    out = [base]
    # "Andrew Dung-Lac and Companions" -> also try just "Andrew Dung-Lac"
    trimmed = re.sub(r"\s+and\s+(his\s+)?(companions?|others)\s*$", "", base, flags=re.I)
    if trimmed != base:
        out.append(trimmed)
    return [n for n in dict.fromkeys(out) if n]


def _cached(key: str):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, f"{key}.json")


def http_json(url: str, key: str, retries: int = 5):
    """GET JSON with disk cache and exponential backoff."""
    path = _cached(key)
    if os.path.exists(path):
        with open(path, encoding="utf8") as fh:
            return json.load(fh)
    delay = 5
    last = None
    for _ in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urlopen(req, timeout=120) as resp:
                payload = json.load(resp)
            with open(path, "w", encoding="utf8") as fh:
                json.dump(payload, fh)
            time.sleep(2.0)
            return payload
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"    retry in {delay}s ({exc})", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise RuntimeError(f"gave up after {retries} attempts: {last}")


def sparql(query: str) -> list[dict]:
    """Cache key is a hash of the query, so editing a query invalidates it."""
    key = "q_" + hashlib.sha1(query.encode("utf8")).hexdigest()[:16]
    payload = http_json(f"{ENDPOINT}?format=json&query={quote(query)}", key)
    return payload["results"]["bindings"]


def val(row: dict, k: str) -> str:
    return row[k]["value"] if row.get(k) else ""


def qid_of(row: dict, k: str) -> str:
    return val(row, k).rsplit("/", 1)[-1]


def parse_point(wkt: str) -> tuple[str, str]:
    """'Point(12.45 41.90)' -> ('41.90', '12.45'). Wikidata puts lon first."""
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt or "")
    return (m.group(2), m.group(1)) if m else ("", "")


# ------------------------------------------------------- our existing saints

def load_our_saints() -> list[dict]:
    saints, bad_encoding = [], []

    export = os.path.join(REPO, "tools", "catalog_export.json")
    if os.path.exists(export):
        with open(export, encoding="utf8") as fh:
            for s in json.load(fh)["saints"]:
                if "�" in s["title"]:
                    bad_encoding.append(s["title"])
                saints.append({"title": s["title"], "slug": s["slug"], "source": "original"})

    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("pip install openpyxl")

    book = os.path.join(REPO, "tools", "SitesOfGrace_Saints_EXPANSION_2026-09.xlsx")
    if os.path.exists(book):
        ws = load_workbook(book, read_only=True, data_only=True)["Saints"]
        header = list(next(ws.iter_rows(values_only=True)))
        for raw in ws.iter_rows(min_row=2, values_only=True):
            row = dict(zip(header, raw))
            if row.get("name"):
                saints.append({"title": row["name"], "slug": row["slug"], "source": "expansion"})

    seen, unique = set(), []
    for s in saints:
        if s["slug"] not in seen:
            seen.add(s["slug"])
            unique.append(s)

    if bad_encoding:
        print(f"!! {len(bad_encoding)} names in catalog_export.json contain U+FFFD "
              f"replacement characters and will not match:")
        for t in bad_encoding[:10]:
            print(f"     {t!r}")
        print("   Regenerate that file reading the dump as UTF-8 without errors='replace'.\n")
    return unique


# ------------------------------------------------------------------ matching

LABEL_QUERY = """
SELECT ?item ?itemLabel ?name ?status WHERE {{
  VALUES ?name {{ {names} }}
  {{ ?item rdfs:label ?name. }} UNION {{ ?item skos:altLabel ?name. }}
  ?item wdt:{instance} ?cls.
  VALUES ?cls {{ {classes} }}
  OPTIONAL {{ ?item wdt:{status} ?status. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
# ?status is OPTIONAL rather than required on purpose. Requiring P411 would
# drop saints Wikidata has not tagged with a canonization status at all, which
# is common for biblical figures. Instead we ask for it and PREFER candidates
# that have one — that is what collapses "Agnes" from 170 candidates to the
# handful the Church actually canonized, without losing the untagged ones.


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def match_by_label(names: list[str], batch: int = 80) -> dict[str, list[tuple[str, str, bool]]]:
    """name -> [(qid, label, is_canonized)]. Small queries on the label index."""
    found: dict[str, dict[str, tuple[str, str, bool]]] = {}
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        print(f"  labels {i + 1}-{i + len(chunk)} of {len(names)}")
        rows = sparql(LABEL_QUERY.format(
            names=" ".join(f'"{escape(n)}"@en' for n in chunk),
            instance=P_INSTANCE, classes=" ".join(CLASSES), status=P_STATUS))
        for row in rows:
            name, q = val(row, "name"), qid_of(row, "item")
            bucket = found.setdefault(name, {})
            canonized = bool(val(row, "status"))
            prev = bucket.get(q)
            # One item can appear on several rows (multiple statuses); keep
            # canonized=True if any row says so.
            bucket[q] = (q, val(row, "itemLabel"), canonized or (prev[2] if prev else False))
    return {name: list(items.values()) for name, items in found.items()}


def narrow(candidates: list[tuple[str, str, bool]]) -> list[tuple[str, str, bool]]:
    """Prefer candidates Wikidata records a canonization status for.

    "Agnes" matches 170 humans; only a couple are canonized. If exactly one
    candidate is canonized, that is our saint. If several are, it stays
    ambiguous and a human decides. If none are, fall back to the full list —
    some genuine saints carry no P411 at all.
    """
    canonized = [c for c in candidates if c[2]]
    return canonized if canonized else candidates


def search_fallback(name: str) -> list[tuple[str, str]]:
    """wbsearchentities for names no exact label matched. Cheap and fuzzy."""
    url = SEARCH_API + "?" + urlencode({
        "action": "wbsearchentities", "search": name, "language": "en",
        "type": "item", "limit": 5, "format": "json"})
    key = "s_" + hashlib.sha1(name.encode("utf8")).hexdigest()[:16]
    try:
        payload = http_json(url, key)
    except RuntimeError:
        return []
    return [(hit["id"], hit.get("label", "")) for hit in payload.get("search", [])]


# ------------------------------------------------------------------- details

DETAIL_QUERY = """
SELECT ?item ?feast ?birth ?death ?burialLabel ?coord ?orderLabel
       ?patronageLabel ?image ?commons ?statusLabel
WHERE {{
  VALUES ?item {{ {items} }}
  OPTIONAL {{ ?item wdt:{feast} ?feast. }}
  OPTIONAL {{ ?item wdt:{birth} ?birth. }}
  OPTIONAL {{ ?item wdt:{death} ?death. }}
  OPTIONAL {{ ?item wdt:{burial} ?burial. OPTIONAL {{ ?burial wdt:{coord} ?coord. }} }}
  OPTIONAL {{ ?item wdt:{order} ?order. }}
  OPTIONAL {{ ?item wdt:{patronage} ?patronage. }}
  OPTIONAL {{ ?item wdt:{image} ?image. }}
  OPTIONAL {{ ?item wdt:{commons} ?commons. }}
  OPTIONAL {{ ?item wdt:{status} ?status. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def fetch_details(qids: list[str], batch: int = 40) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(qids), batch):
        chunk = qids[i:i + batch]
        print(f"  details {i + 1}-{i + len(chunk)} of {len(qids)}")
        rows = sparql(DETAIL_QUERY.format(
            items=" ".join(f"wd:{q}" for q in chunk),
            feast=P_FEAST, birth=P_BIRTH, death=P_DEATH, burial=P_BURIAL,
            coord=P_COORD, order=P_ORDER, patronage=P_PATRONAGE,
            image=P_IMAGE, commons=P_COMMONS, status=P_STATUS))
        for row in rows:
            q = qid_of(row, "item")
            rec = out.setdefault(q, {"qid": q, "burial": "", "coord": "", "image": "",
                                     "commons": "", "feast": "", "birth": "", "death": "",
                                     "order": set(), "patronage": set(), "status": set()})
            for field, key in (("feast", "feast"), ("birth", "birth"), ("death", "death"),
                               ("image", "image"), ("commons", "commons"),
                               ("burial", "burialLabel"), ("coord", "coord")):
                if not rec[field] and val(row, key):
                    rec[field] = val(row, key)
            for field, key in (("order", "orderLabel"), ("patronage", "patronageLabel"),
                               ("status", "statusLabel")):
                if val(row, key):
                    rec[field].add(val(row, key))
    return out


def resolve(ours: list[dict]) -> tuple[list[dict], list[dict]]:
    """Two passes: exact label/alias, then the search API for the leftovers."""
    wanted: dict[str, list[dict]] = {}
    for s in ours:
        for name in search_names(s["title"]):
            wanted.setdefault(name, []).append(s)

    print(f"resolving {len(wanted)} candidate names for {len(ours)} saints")
    hits = match_by_label(sorted(wanted))

    matched, unresolved = {}, []
    for s in ours:
        candidates: list[tuple[str, str, bool]] = []
        for name in search_names(s["title"]):
            candidates.extend(hits.get(name, []))
        uniq = narrow(list(dict.fromkeys(candidates)))
        if len(uniq) == 1:
            matched[s["slug"]] = {**s, "qid": uniq[0][0], "wd_label": uniq[0][1],
                                  "confidence": "label" if uniq[0][2] else "label-nostatus"}
        elif len(uniq) > 1:
            # Still ambiguous after preferring canonized candidates. Record the
            # options but mark it clearly — nothing downstream should trust it.
            matched[s["slug"]] = {**s, "qid": uniq[0][0], "wd_label": uniq[0][1],
                                  "confidence": f"AMBIGUOUS {len(uniq)}: "
                                                + ",".join(q for q, _, _ in uniq[:4])}
        else:
            unresolved.append(s)

    print(f"  exact label match: {len(matched)}; trying search API on {len(unresolved)}")
    still = []
    for s in unresolved:
        results = search_fallback(search_names(s["title"])[0])
        pick = next((r for r in results if fold(r[1]) == fold(s["title"])), None)
        if pick:
            matched[s["slug"]] = {**s, "qid": pick[0], "wd_label": pick[1],
                                  "confidence": "search"}
        else:
            still.append({**s, "qid": "", "wd_label": "",
                          "confidence": "no match" if not results
                          else "search only: " + ",".join(f"{q}={l}" for q, l in results[:3])})
    return list(matched.values()), still


# --------------------------------------------------------------------- modes

def write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def flatten(m: dict, d: dict) -> dict:
    lat, lon = parse_point(d.get("coord", ""))
    return {**m, "burial": d.get("burial", ""), "lat": lat, "lon": lon,
            "order": "; ".join(sorted(d.get("order", []))),
            "patronage_wd": "; ".join(sorted(d.get("patronage", []))),
            "status": "; ".join(sorted(d.get("status", []))),
            "image_url": d.get("image", ""), "commons": d.get("commons", ""),
            "feast_raw": d.get("feast", ""),
            "source_url": f"https://www.wikidata.org/wiki/{m['qid']}" if m.get("qid") else ""}


def run_probe() -> None:
    ours = load_our_saints()
    print(f"our saints: {len(ours)}\n")
    matched, missing = resolve(ours)
    pct = 100 * len(matched) // max(len(ours), 1)
    print(f"\nMATCHED {len(matched)} / {len(ours)}  ({pct}%)")

    details = fetch_details([m["qid"] for m in matched])
    cover = Counter()
    for m in matched:
        d = details.get(m["qid"], {})
        for f in ("burial", "coord", "order", "patronage", "image", "feast", "birth", "death"):
            if d.get(f):
                cover[f] += 1

    print("\n--- FIELD COVERAGE (of matched saints) ---")
    total = max(len(matched), 1)
    for f in ("burial", "coord", "order", "patronage", "image", "feast", "birth", "death"):
        print(f"  {f:12} {cover[f]:4}/{total}  {100 * cover[f] // total:3}%")
    print("\n`coord` is the number that matters: that is how many saints can become")
    print("a pin on the map, and it decides whether the schema change is worth it.\n")

    rows = [flatten(m, details.get(m["qid"], {})) for m in matched]
    rows += [flatten(m, {}) for m in missing]
    write_csv(os.path.join(HERE, "match_report.csv"), rows,
              ["title", "slug", "source", "qid", "wd_label", "confidence", "status",
               "burial", "lat", "lon", "order", "image_url", "source_url"])

    shaky = [r for r in rows if r["confidence"] not in ("label", "search")]
    print(f"{len(shaky)} rows need a human eye (ambiguous or unmatched).")


def run_enrich() -> None:
    ours = load_our_saints()
    matched, _ = resolve(ours)
    details = fetch_details([m["qid"] for m in matched])
    rows = [flatten(m, details.get(m["qid"], {})) for m in matched]
    write_csv(os.path.join(HERE, "enrichment.csv"), rows,
              ["slug", "title", "wd_label", "confidence", "qid", "burial", "lat", "lon",
               "order", "patronage_wd", "image_url", "commons", "feast_raw", "source_url"])


# Catholic-only filter for --expand. P411 (canonization status) is used by
# Wikidata across religions — Hindu, Orthodox, Islamic figures all carry it —
# so filtering on "has P411" alone (the old behaviour) let non-Catholic
# figures like A. C. Bhaktivedanta Swami Prabhupada and Alexander Nevsky into
# candidates.csv. Two independent Catholic-specific signals, combined with
# OR because either alone misses real Catholic saints: P140 (religion) tagged
# one of these Catholic denominations, OR the canonization status itself is
# literally "Catholic saint" (Q3464126) regardless of religion tagging (some
# saints carry the status but not a religion property). Verified 2026-09-23
# against an explicit must-include/must-exclude list — see run_expand's
# docstring and the conversation this shipped from.
CATHOLIC_RELIGIONS = ["wd:Q1841", "wd:Q9592", "wd:Q597526", "wd:Q49376"]
# Catholicism, Catholic Church, Latin Church, Eastern Catholic Churches
CATHOLIC_SAINT_STATUS = "wd:Q3464126"  # "Catholic saint"

EXPAND_QUERY = """
SELECT ?item ?itemLabel ?burialLabel ?coord ?image ?links WHERE {{
  {{
    ?item wdt:{status} ?status.
    VALUES ?religion {{ {religions} }}
    ?item wdt:P140 ?religion.
  }} UNION {{
    ?item wdt:{status} {catholic_status}.
  }}
  ?item wdt:{burial} ?burial.
  ?burial wdt:{coord} ?coord.
  ?item wikibase:sitelinks ?links.
  OPTIONAL {{ ?item wdt:{image} ?image. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY DESC(?links)
LIMIT {limit} OFFSET {offset}
"""


def run_expand(limit: int) -> None:
    """Catholic saints we do not have, with a mapped burial place, ranked by
    Wikipedia sitelink count (the standard notability proxy — a real number,
    unlike the old constant score that left every row tied and the sort
    alphabetical).

    Catholic-only: see CATHOLIC_RELIGIONS/CATHOLIC_SAINT_STATUS above.
    """
    ours = load_our_saints()
    have = {fold(s["title"]) for s in ours}

    collected: dict[str, dict] = {}
    for page in range(12):
        offset = page * 500
        print(f"  candidates page {page + 1}")
        rows = sparql(EXPAND_QUERY.format(
            status=P_STATUS, religions=" ".join(CATHOLIC_RELIGIONS),
            catholic_status=CATHOLIC_SAINT_STATUS, burial=P_BURIAL, coord=P_COORD,
            image=P_IMAGE, limit=500, offset=offset))
        if not rows:
            break
        for row in rows:
            q = qid_of(row, "item")
            collected.setdefault(q, {
                "name": val(row, "itemLabel"), "qid": q,
                "burial": val(row, "burialLabel"), "coord": val(row, "coord"),
                "image_url": val(row, "image"),
                "sitelinks": int(val(row, "links") or 0)})
        if len(rows) < 500:
            break

    fresh = [c for c in collected.values()
             if c["name"] and not c["name"].startswith("Q") and fold(c["name"]) not in have]
    for c in fresh:
        c["lat"], c["lon"] = parse_point(c["coord"])
        c["source_url"] = f"https://www.wikidata.org/wiki/{c['qid']}"
    fresh.sort(key=lambda r: (-r["sitelinks"], r["name"]))

    print(f"\n{len(collected)} Catholic saints with a mapped burial place; "
          f"{len(fresh)} we do not already have.")
    write_csv(os.path.join(HERE, "candidates.csv"), fresh[:limit],
              ["name", "qid", "sitelinks", "burial", "lat", "lon", "image_url", "source_url"])


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--probe", action="store_true")
    g.add_argument("--enrich", action="store_true")
    g.add_argument("--expand", action="store_true")
    ap.add_argument("--limit", type=int, default=700)
    a = ap.parse_args()
    run_probe() if a.probe else run_enrich() if a.enrich else run_expand(a.limit)


if __name__ == "__main__":
    main()
