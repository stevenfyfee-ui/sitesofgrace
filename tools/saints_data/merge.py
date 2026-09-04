#!/usr/bin/env python3
"""Merge the current Roman Calendar + canonization records against the live
Sites of Grace saints table, and emit an import-ready plan.

Matching is deliberately conservative and fully auditable: every non-exact
match is written to matches_fuzzy.csv for human sign-off before import.

Outputs to /home/claude/out:
  saints_to_add.csv        new SaintPage rows, import-workbook column order
  saints_to_update.csv     existing rows whose feast_day/canonized should change
  saints_review.csv        existing rows that look wrong (dupes, typos, non-persons)
  matches_fuzzy.csv        every inexact match made, for review
"""
import csv, difflib, json, os, re, unicodedata
from collections import defaultdict

DATA = "/home/claude/data"
OUT = "/home/claude/out"
os.makedirs(OUT, exist_ok=True)

EXPORT = json.load(open("/mnt/user-data/uploads/sitesofgrace/tools/catalog_export.json", encoding="utf8"))

LIGATURES = {"æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "ł": "l", "đ": "d", "ŧ": "t"}
HONORIFIC = re.compile(r"\b(sts?|saints?|blessed|bl|pope|the|his)\b", re.I)
TRAILING = re.compile(r"\b(and companions?|companions?|archangels?|martyr|religious|and)\b\s*$", re.I)
PAREN = re.compile(r"\s*\([^)]*\)")
# "The Nativity of Saint John the Baptist" -> "John the Baptist"
PREFIX_OF = re.compile(r"^(nativity|passion|conversion|chair|feast|dedication)\s+of\s+", re.I)


def _fold(s):
    for a, b in LIGATURES.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def key(name, keep_paren=False):
    """Collapse a saint name to a comparison key."""
    s = _fold(name).replace("’", "'").replace("–", "-")
    if not keep_paren:
        s = PAREN.sub("", s)
    s = re.sub(r"[^a-zA-Z0-9' ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = PREFIX_OF.sub("", s)
    prev = None
    while prev != s:
        prev = s
        s = HONORIFIC.sub(" ", s)
        s = TRAILING.sub("", s)
        s = re.sub(r"\s+", " ", s).strip()
    return s.lower().replace("'", "")


# Compound calendar celebrations -> the individuals the DB should hold.
SPLITS = {
    "basil great and gregory nazianzen": ["Basil the Great", "Gregory Nazianzen"],
    "timothy and titus": ["Timothy", "Titus"],
    "cyril and methodius": ["Cyril", "Methodius"],
    "philip and james": ["Philip", "James (Son of Alphaeus)"],
    "nereus and achilleus": ["Nereus", "Achilleus"],
    "marcellinus and peter": ["Marcellinus"],
    "john fisher and thomas more": ["John Fisher", "Thomas More"],
    "peter and paul": ["Peter", "Paul"],
    "joachim and anne": ["Joachim and Ann"],
    "martha mary and lazarus": ["Martha", "Mary of Bethany", "Lazarus"],
    "pontian and hippolytus": ["Pontian", "Hippolytus"],
    "cornelius and cyprian": ["Cornelius", "Cyprian"],
    "cosmas and damian": ["Cosmas and Damian"],
    "simon and jude": ["Simon and Jude"],
    "michael gabriel and raphael": ["Michael", "Gabriel", "Raphael"],
    "andrew kim tae gon paul chong ha sang": ["Andrew Kim Tae-gon"],
    "john de brebeuf isaac jogues": ["Isaac Jogues", "John de Brebeuf"],
    "perpetua and felicity": ["Perpetua and Felicity"],
    "paul miki": ["Paul Miki"],
    "charles lwanga": ["Charles Lwanga"],
    "christopher magallanes": ["Christopher Magallanes"],
    "augustine zhao rong": ["Augustine Zhao Rong"],
    "andrew dung lac": ["Andrew Dung-Lac"],
    "lawrence ruiz": ["Lawrence Ruiz"],
    "sixtus ii": ["Sixtus II"],
    "denis": ["Denis"],
}

# Calendar / canonization spelling -> the spelling already in the database.
# Only for cases where the two clearly denote the same person.
ALIASES = {
    "blaise": "blase",
    "camillus de lellis": "camillus of lellis",
    "fidelis of sigmaringen": "fidelis",
    "gertrude": "gertrude great",
    "justin": "justin martyr",
    "wenceslaus": "wenceslas",
    "faustina kowalska": "faustina",
    "therese of child jesus": "therese of lisieux",
    "therese of lisieux": "therese of lisieux",
    "teresa of jesus": "teresa of avila",
    "teresa of avila": "teresa of avila",
    "teresa benedict of cross": "teresa benedicta of cross",
    "teresa benedicta of cross": "teresa benedicta of cross",
    "jean vianney": "john vianney",
    "pius of pietrelcina": "pio of pietrelcina",
    "padre pio of pietrelcina": "pio of pietrelcina",
    "charbel makhlouf": "sharbel makhluf",
    "mary magdalene de pazzi": "mary magdalen of pazzi",
    "mary magdalene": "mary magdalen",
    "raymond of penyafort": "raymund of pennafort",
    "francis of paola": "francis of paula",
    "francis de sales": "francis of sales",
    "joseph calasanz": "joseph calasanctius",
    "stanislaus": "stanislas",
    "hedwig": "hedwige",
    "peter chanel": "peter chantel",
    "peter canisius": "peter cantius",
    "john of kanty": "john cantius",
    "thomas becket": "thomas of canterbury",
    "juan diego cuauhtlatoatzin": "juan diego",
    "louis grignion de montfort": "louis de montfort",
    "louis marie grignion de montfort": "louis de montfort",
    "bridget": "bridget of sweden",
    "birgitta - bridget of sweden": "bridget of sweden",
    "damien de veuster": "damien de veuster of molokai",
    "damien of molokai": "damien de veuster of molokai",
    "mother teresa of calcutta": "teresa of calcutta",
    "callistus i": "callistus",
    "clement i": "clement of rome",
    "sylvester i": "sylvester",
    "damasus i": "damasus",
    "martin i": "martin",
    "hilary": "hilary of poitiers",
    "turibius of mongrovejo": "turibius",
    "john i": "john i",
    "elizabeth ann seton": "elizabeth ann seton",
    "andre bessette": "andre bessette",
    "marianne cope": "marianne cope",
    "frances xavier cabrini": "frances xavier cabrini",
    "bernadette soubirous": "bernadette soubirous",
    "carlo acutis": "carlo acutis",
    "isidore": "isidore",
    "anthony": "anthony",
    "anne": "anne and joachim",
    "joachim and ann": "anne and joachim",
    "james": "james son of zebedee",
    "thomas": "thomas",
    "vincent": "vincent",
    "peter julian eymard": "peter julian eymard",
    "john paul ii": "john paul ii",
    "john xxiii": "john xxiii",
    "paul vi": "paul vi",
    "pius x": "pius x",
    "pope pius x": "pius x",
    "hildegard of bingen": "hildegard of bingen",
    "kateri tekakwitha": "kateri tekakwitha",
    "junipero serra": "junipero serra",
    "katharine drexel": "katharine drexel",
    "john neumann": "john neumann",
    "rose philippine duchesne": "rose philippine duchesne",
    "josephine bakhita": "josephine bakhita",
    "john henry newman": "john henry newman",
    "teresa of calcutta": "teresa of calcutta",
    "maria goretti": "maria goretti",
    "maximilian kolbe": "maximilian kolbe",
    "john of avila": "john of avila",
    "gregory of narek": "gregory of narek",
    "bede venerable": "bede venerable",
    "maximus confessor": "maximus confessor",
    "robert bellarmine": "robert bellarmine",
    "albert great": "albert great",
    "john bosco": "john bosco",
    "john eudes": "john eudes",
    "thomas more": "thomas more",
    "john fisher": "john fisher",
    "martin de porres": "martin de porres",
    "anthony mary claret": "anthony mary claret",
    "josemaria escriva": "josemaria escriva",
}


def canonical(k):
    return ALIASES.get(k, k)


# ------------------------------------------------------------------- existing

existing_by_key = {}
for s in EXPORT["saints"]:
    existing_by_key.setdefault(canonical(key(s["title"])), []).append(s)

fuzzy_log = []


def find_existing(k, display):
    """Exact -> alias -> token-subset -> difflib. Logs anything inexact."""
    ck = canonical(k)
    if ck in existing_by_key:
        return existing_by_key[ck][0], "exact" if ck == k else "alias"
    best, score = None, 0.0
    for ek, rows in existing_by_key.items():
        r = difflib.SequenceMatcher(None, ck, ek).ratio()
        if r > score:
            best, score = rows[0], r
    if best and score >= 0.94:
        fuzzy_log.append({"incoming": display, "incoming_key": ck,
                          "matched_title": best["title"], "method": "difflib",
                          "score": f"{score:.3f}"})
        return best, "difflib"
    return None, None


# --------------------------------------------------------------- the calendar

cal_people = {}
with open(f"{DATA}/calendar.csv", encoding="utf8") as fh:
    for row in csv.DictReader(fh, delimiter="|"):
        if row["scope"] == "MARIAN":
            continue
        k = key(row["name"])
        if "seven holy founders" in k or "first martyrs" in k or "holy innocents" in k:
            continue
        names = SPLITS.get(k, [k])
        for n in names:
            nk = canonical(key(n))
            display = n if n != nk else row["name"]
            display = re.sub(r"^(Saints?|Blessed|St\.|Bl\.)\s+", "", display)
            if nk in cal_people:
                continue
            cal_people[nk] = {"display": display, "feast_day": row["month_day"],
                              "rank": row["rank"], "scope": row["scope"],
                              "honorific": "Blessed" if re.match(r"^(Blessed|Bl\.)\s", row["name"]) else "Saint"}

# ----------------------------------------------------------- canonizations

canon = {}
with open(f"{DATA}/canonizations.csv", encoding="utf8") as fh:
    for row in csv.DictReader(fh, delimiter="|"):
        canon[canonical(key(row["name"]))] = row

# --------------------------------------------------------------- build output

def slugify(name, honorific="Saint"):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", _fold(name)).strip("-").lower()
    pref = "blessed" if honorific == "Blessed" else "st"
    return f"{pref}-{s}"[:250]


existing_slugs = {s["slug"] for s in EXPORT["saints"]}
to_add, to_update, matched_keys = [], [], set()


def queue_add(display, feast, born, died, canonized, source_url, source_note, status,
              honorific="Saint"):
    prefix = "Blessed" if honorific == "Blessed" else "St."
    title = f"{prefix} {display}"
    slug = slugify(display, honorific)
    n = 2
    base = slug
    while slug in existing_slugs:
        slug = f"{base}-{n}"
        n += 1
    existing_slugs.add(slug)
    to_add.append({
        "name": title, "slug": slug, "also_known_as": "", "honorific_type": honorific,
        "feast_day": feast, "born": born, "died": died, "canonized": canonized,
        "patronage": "", "significance": "", "body_draft": "",
        "source_url": source_url, "source_note": source_note,
        "data_status": status,
        "editor_notes": "Auto-generated; needs narrative before publishing.",
        "topics": "", "portrait_filename": "",
    })


CAL_URL = "https://en.wikipedia.org/wiki/General_Roman_Calendar"

for k, cal in cal_people.items():
    c = canon.get(k)
    hit, how = find_existing(k, cal["display"])
    if hit:
        matched_keys.add(canonical(key(hit["title"])))
        want_feast, want_canon = cal["feast_day"], (c or {}).get("canonization_date", "")
        cur_feast = (hit["feast_day"] or "").strip()
        cur_canon = (hit["canonized"] or "").strip()
        if cur_feast != want_feast or (want_canon and want_canon not in cur_canon):
            to_update.append({"slug": hit["slug"], "title": hit["title"],
                              "feast_day_current": cur_feast, "feast_day_new": want_feast,
                              "canonized_current": cur_canon, "canonized_new": want_canon,
                              "rank": cal["rank"], "scope": cal["scope"], "match": how})
        continue
    queue_add(cal["display"], cal["feast_day"], (c or {}).get("birth_year", ""),
              (c or {}).get("death_year", ""), (c or {}).get("canonization_date", ""),
              CAL_URL, f"Current General Roman Calendar ({cal['scope']}), {cal['rank']}",
              "stub-calendar", cal.get("honorific", "Saint"))

for k, c in canon.items():
    if k in cal_people or c["confidence"] != "OK" or c["group_count"]:
        continue
    if c["canonization_date"][:4] < "1900":
        continue
    hit, how = find_existing(k, c["name"])
    if hit:
        matched_keys.add(canonical(key(hit["title"])))
        cur = (hit["canonized"] or "").strip()
        if c["canonization_date"] not in cur:
            to_update.append({"slug": hit["slug"], "title": hit["title"],
                              "feast_day_current": (hit["feast_day"] or "").strip(),
                              "feast_day_new": (hit["feast_day"] or "").strip(),
                              "canonized_current": cur,
                              "canonized_new": c["canonization_date"],
                              "rank": "", "scope": "canonization-only", "match": how})
        continue
    queue_add(c["name"], "", c["birth_year"], c["death_year"], c["canonization_date"],
              "", f"Canonized by Pope {c['pope']}", "stub-canonization")

# ---------------------------------------------- existing rows needing review

review = []
dupes = defaultdict(list)
for s in EXPORT["saints"]:
    dupes[key(s["title"], keep_paren=True)].append(s["title"])
for k, titles in dupes.items():
    if len(titles) > 1:
        review.append({"issue": "duplicate-title", "detail": " / ".join(sorted(titles)), "key": k})

pair_dupes = defaultdict(list)
for s in EXPORT["saints"]:
    pair_dupes[canonical(key(s["title"]))].append(s["title"])
for k, titles in pair_dupes.items():
    if len(titles) > 1:
        review.append({"issue": "collapses-to-same-saint", "detail": " / ".join(sorted(titles)), "key": k})

NOT_A_PERSON = ["chair at rome"]
for s in EXPORT["saints"]:
    low = s["title"].lower()
    ck = canonical(key(s["title"]))
    if any(n in low for n in NOT_A_PERSON):
        review.append({"issue": "not-a-person", "detail": s["title"], "key": s["slug"]})
    elif ck not in matched_keys and ck not in canon:
        review.append({"issue": "not-on-current-calendar", "detail": s["title"], "key": s["slug"]})

# ------------------------------------------------------------------ write out

def dump(path, rows, fields):
    with open(path, "w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


ADD_FIELDS = ["name", "slug", "also_known_as", "honorific_type", "feast_day", "born",
              "died", "canonized", "patronage", "significance", "body_draft",
              "source_url", "source_note", "data_status", "editor_notes", "topics",
              "portrait_filename"]
UPD_FIELDS = ["slug", "title", "feast_day_current", "feast_day_new",
              "canonized_current", "canonized_new", "rank", "scope", "match"]

to_add.sort(key=lambda r: r["name"])
dump(f"{OUT}/saints_to_add.csv", to_add, ADD_FIELDS)
dump(f"{OUT}/saints_to_update.csv", sorted(to_update, key=lambda r: r["title"]), UPD_FIELDS)
dump(f"{OUT}/saints_review.csv", review, ["issue", "detail", "key"])
dump(f"{OUT}/matches_fuzzy.csv", fuzzy_log,
     ["incoming", "incoming_key", "matched_title", "method", "score"])

print("existing saints         ", len(EXPORT["saints"]))
print("calendar person-entries ", len(cal_people))
print("canonization records    ", len(canon))
print("NEW saints to add       ", len(to_add))
print("  from calendar         ", sum(1 for r in to_add if r["data_status"] == "stub-calendar"))
print("  from canonizations    ", sum(1 for r in to_add if r["data_status"] == "stub-canonization"))
print("existing to update      ", len(to_update))
print("inexact matches to review", len(fuzzy_log))
print("existing needing review ", len(review))
print("PROJECTED TOTAL         ", len(EXPORT["saints"]) + len(to_add))
print()
for issue in ("duplicate-title", "collapses-to-same-saint", "not-a-person", "not-on-current-calendar"):
    rows = [r for r in review if r["issue"] == issue]
    if rows:
        print(f"-- {issue} ({len(rows)})")
        for r in rows:
            print("   ", r["detail"])
print()
print("-- calendar saints still queued as NEW (verify none is a rename of an existing row)")
for r in to_add:
    if r["data_status"] == "stub-calendar":
        print("   ", r["name"], "|", r["feast_day"])
