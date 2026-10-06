"""Match our saint and site pages to days of the year.

feast_day and date_display are free text typed by editors, so the parser is
deliberately narrow: it recognises an explicit month + day, or one of the
movable feasts listed in MOVABLE_FEASTS, and returns nothing for anything
else. A value it can't read shows up in `manage.py audit_feast_dates`
instead of being guessed at.
"""
import re
import unicodedata
from datetime import date

from django.core.cache import cache

from catalog.text import fold

INDEX_CACHE_KEY = "liturgy:day-index:v1"
INDEX_TTL = 15 * 60

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
# Longest names first so "sept" wins over "sep" and "june" over "jun".
_MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{3,4}))?"
# "October 7" / "Oct. 7th" / "7 October", each optionally followed by a year.
_DATE_RE = re.compile(
    rf"\b{_MONTH}\s+{_DAY}\b{_YEAR}(?!\d)|\b{_DAY}\s+{_MONTH}(?![a-z]){_YEAR}(?!\d)",
    re.I,
)
# What may sit between a yearless date and a dated one for the year to carry
# back: "May 13 – October 13, 1917".
_RANGE_GAP = re.compile(r"^\s*(?:[-–—/&,;]|to|through|thru|and|until)\s*$", re.I)

# Lowercase phrase -> LitCal event_key. Keys taken from
# liturgy/data/litcal-US-2026.json, not from memory.
MOVABLE_FEASTS = {
    "divine mercy sunday": "Easter2",
    "second sunday of easter": "Easter2",
    "pentecost": "Pentecost",
    "pentecost sunday": "Pentecost",
    "trinity sunday": "Trinity",
    "holy trinity sunday": "Trinity",
    "most holy trinity": "Trinity",
    "corpus christi": "CorpusChristi",
    "most holy body and blood of christ": "CorpusChristi",
    "body and blood of christ": "CorpusChristi",
    "sacred heart": "SacredHeart",
    "sacred heart of jesus": "SacredHeart",
    "most sacred heart of jesus": "SacredHeart",
    "immaculate heart": "ImmaculateHeart",
    "immaculate heart of mary": "ImmaculateHeart",
    "immaculate heart of the blessed virgin mary": "ImmaculateHeart",
    "christ the king": "ChristKing",
    "christ king of the universe": "ChristKing",
    "holy family": "HolyFamily",
    "baptism of the lord": "BaptismLord",
    "ascension": "Ascension",
    "ascension of the lord": "Ascension",
    "ascension thursday": "Ascension",
    "easter": "Easter",
    "easter sunday": "Easter",
    "ash wednesday": "AshWednesday",
    "palm sunday": "PalmSun",
    "holy thursday": "HolyThurs",
    "good friday": "GoodFri",
    "mary mother of the church": "MaryMotherChurch",
    "mother of the church": "MaryMotherChurch",
}
_MOVABLE_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in sorted(MOVABLE_FEASTS, key=len, reverse=True)) + r")\b"
)
# A feast named only as a reference point is a different day:
# "Friday after Ascension", "Easter Monday", "Octave of Easter".
_RELATIVE_BEFORE = re.compile(
    r"\b(after|before|following|preceding|eve|vigil|octave|week|weeks|season|during|until|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)(\s+of)?(\s+the)?\s*$"
)
_RELATIVE_AFTER = re.compile(
    r"^\s*(monday|tuesday|wednesday|thursday|friday|saturday|week|weeks|octave|vigil|eve|"
    r"season|time|triduum|novena)\b"
)


def _norm(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _valid(month, day, year=2000):
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _date_matches(text):
    """(start, end, month, day, year|None) for each explicit date in `text`."""
    found = []
    for m in _DATE_RE.finditer(text or ""):
        if m.group(1):
            month, day, year = MONTHS[m.group(1).lower()], int(m.group(2)), m.group(3)
        else:
            month, day, year = MONTHS[m.group(5).lower()], int(m.group(4)), m.group(6)
        if _valid(month, day):
            found.append((m.start(), m.end(), month, day, int(year) if year else None))
    return found


def parse_feast_text(text):
    """Tokens for a feast_day value.

    ("fixed", month, day) for each explicit date, ("movable", event_key) for
    each movable feast named in words, [] for anything else.
    """
    tokens = [(start, ("fixed", month, day)) for start, _, month, day, _ in _date_matches(text)]
    norm = _norm(text)
    for m in _MOVABLE_RE.finditer(norm):
        if _RELATIVE_BEFORE.search(norm[:m.start()]) or _RELATIVE_AFTER.search(norm[m.end():]):
            continue
        # Offset into the normalised text; only used for ordering.
        tokens.append((m.start(), ("movable", MOVABLE_FEASTS[m.group(1)])))
    out = []
    for _, token in sorted(tokens, key=lambda pair: pair[0]):
        if token not in out:
            out.append(token)
    return out


def parse_anniversaries(date_display):
    """(month, day, year) for each explicit full date in a date_display value.

    "October 13, 1917" and "13 October 1917" count; so does the first date
    in "May 13 – October 13, 1917", which borrows the year after it. A bare
    year or a month and year yields nothing.
    """
    text = date_display or ""
    found = _date_matches(text)
    years = [year for *_, year in found]
    for i in range(len(found) - 2, -1, -1):
        if years[i] is None and years[i + 1] is not None:
            gap = text[found[i][1]:found[i + 1][0]]
            if _RANGE_GAP.match(gap):
                years[i] = years[i + 1]
    return [
        (month, day, year)
        for (_, _, month, day, _), year in zip(found, years)
        if year is not None and _valid(month, day, year)
    ]


def _token_key(token):
    return (token[1], token[2]) if token[0] == "fixed" else token[1]


def _page_ref(page, kind):
    """The little that the card needs from a page, cheap to cache."""
    if kind == "saint":
        meta = page.honorific_type or "Feast day"
        image_id = page.portrait_id
    else:
        meta = ", ".join(part for part in (page.locality, page.country) if part)
        image_id = page.featured_image_id
    return {
        "pk": page.pk,
        "title": page.title,
        "url": page.get_url(),
        "kind": kind,
        "meta": meta,
        "image_id": image_id,
    }


def _build():
    from catalog.models import SacredSitePage, SaintPage

    days, titles = {}, {}

    def add(key, ref, kind, reason, year=None):
        days.setdefault(key, []).append({"page": ref, "kind": kind, "reason": reason, "year": year})

    # live().public() only: unpublished stub saints and pages behind a view
    # restriction never reach the home page.
    for page in SaintPage.objects.live().public().order_by("pk"):
        ref = _page_ref(page, "saint")
        if not ref["url"]:
            continue
        titles.setdefault(fold(page.title), ref)
        for token in parse_feast_text(page.feast_day):
            add(_token_key(token), ref, "saint", "feast")

    for page in SacredSitePage.objects.live().public().order_by("pk"):
        ref = _page_ref(page, "site")
        if not ref["url"]:
            continue
        titles.setdefault(fold(page.title), ref)
        for token in parse_feast_text(page.feast_day):
            add(_token_key(token), ref, "site", "feast")
        for month, day, year in parse_anniversaries(page.date_display):
            add((month, day), ref, "site", "anniversary", year)

    return {"days": days, "titles": titles}


def load_index():
    """{"days": build_day_index(), "titles": {fold(title): ref}}, cached 15 minutes."""
    data = cache.get(INDEX_CACHE_KEY)
    if data is None:
        data = _build()
        cache.set(INDEX_CACHE_KEY, data, INDEX_TTL)
    return data


def build_day_index():
    """Entries keyed by (month, day) and by movable event_key.

    Each entry is {"page": ref, "kind": "saint"|"site",
    "reason": "feast"|"anniversary", "year": int|None}, where ref is a small
    dict (pk, title, url, kind, meta, image_id) rather than the page itself,
    so the cached index stays small and costs no queries to use.
    """
    return load_index()["days"]


def clear_day_index(**kwargs):
    """page_published / page_unpublished handler (see LiturgyConfig.ready)."""
    cache.delete(INDEX_CACHE_KEY)
