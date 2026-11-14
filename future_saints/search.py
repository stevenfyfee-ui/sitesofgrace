"""Future Saints search (kids-safe): published Future Saints pages only.

What is searched: the five learning types, the California Missions hub, the projects guide
and each published Build This Mission project, all under the Future Saints home and live.
Never adult pages, never drafts (a live page's database row is its published version).

The index is a small JSON list (title, type, subtitle, place, the Words to Know words and the
intro's first sentence), cached for INDEX_TTL and dropped on every publish or unpublish of a
Future Saints page (FutureSaintsConfig.ready). The browser fetches it once and filters it
locally for the type-ahead; the no-JavaScript results page matches with the same rules here.

Privacy: nothing about a search is stored. No query logging, no Wagtail search promotions or
hit counts, no analytics, no cookies, no browser storage (test_search).

Matching: accents and case are ignored, every query word must match the START of a word in
the entry, and a query word of 5+ letters may be one letter off (one letter changed, added or
missing), so "fatma" finds Fátima and "carlo" finds Carlo.
"""
import re
import unicodedata
from html import unescape

from django.core.cache import cache
from django.utils.html import strip_tags

INDEX_CACHE_KEY = "future_saints:search_index:v1"
INDEX_TTL = 60 * 10            # also dropped on publish/unpublish; other server processes refresh within this
FUZZY_MIN = 5                  # query words this long may be one letter off
SUGGESTIONS = ("Carlo", "Fátima", "San Diego")      # the placeholder's words, used when each finds something
MAX_SUGGESTIONS = 3

# (group key, heading), in the order the results show them: the header nav's order, then projects.
GROUPS = [
    ("saint", "Saints"),
    ("marian_apparition", "Marian Apparitions"),
    ("eucharistic_miracle", "Eucharistic Miracles"),
    ("holy_land", "Holy Land"),
    ("california_mission", "California Missions"),
    ("project", "Build This Mission"),
]
GROUP_ICONS = {"saint": "saint", "marian_apparition": "mary", "eucharistic_miracle": "miracle",
               "holy_land": "holyland", "california_mission": "mission", "project": "church"}

# Weights for ranking: a match in the title counts most.
FIELD_WEIGHTS = (("t", 4), ("p", 2), ("s", 1), ("w", 1), ("i", 1))


def fold(text):
    """Lower case, accents removed: "Fátima" -> "fatima"."""
    plain = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()


def words(text):
    return re.findall(r"[a-z0-9]+", fold(text))


def first_sentence(html):
    text = " ".join(unescape(strip_tags(html or "")).split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


def _within_one(a, b):
    """True when a and b differ by at most one letter changed, added or missing."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


def word_score(query_word, entry_word):
    """2 for an exact word-start match, 1 for a one-letter-off one, 0 for none."""
    if entry_word.startswith(query_word):
        return 2
    if len(query_word) >= FUZZY_MIN:
        n = len(query_word)
        for size in (n - 1, n, n + 1):
            if size <= len(entry_word) and _within_one(query_word, entry_word[:size]):
                return 1
    return 0


def score(entry, query_words):
    """0 unless every query word matches the start of some word in the entry."""
    total = 0
    for q in query_words:
        best = 0
        for field, weight in FIELD_WEIGHTS:
            value = entry.get(field) or ""
            for w in words(" ".join(value) if isinstance(value, list) else value):
                best = max(best, word_score(q, w) * weight)
        if not best:
            return 0
        total += best
    return total


def search(index, query):
    query_words = words(query)
    if not query_words:
        return []
    scored = [(score(e, query_words), e) for e in index]
    return [e for s, e in sorted((x for x in scored if x[0]), key=lambda x: (-x[0], fold(x[1]["t"])))]


def grouped(results):
    labels = dict(GROUPS)
    return [{"key": k, "label": labels[k], "icon": GROUP_ICONS[k], "items": [r for r in results if r["k"] == k]}
            for k, _ in GROUPS if any(r["k"] == k for r in results)]


def suggestions(index):
    """Up to three words that find something: the placeholder's, then published titles."""
    found = [s for s in SUGGESTIONS if search(index, s)]
    for entry in index:
        if len(found) >= MAX_SUGGESTIONS:
            break
        name = entry["n"]
        if name and entry["k"] != "project" and not any(fold(f) in fold(name) for f in found):
            found.append(name)
    return found[:MAX_SUGGESTIONS]


# --- the index -------------------------------------------------------------------------------

def _place(page):
    """A place to match for a learning page ("San Diego", "Lourdes, France"), never travel text."""
    from .worldmap import SITE_KINDS, _site_place, saint_place

    if page.content_kind == "saint":
        site, _ = saint_place(page)
        return " ".join(v for v in (site.title, _site_place(site)) if v) if site else ""
    site = page.canonical_page
    if site is None:
        return ""
    if page.content_kind in SITE_KINDS or page.content_kind == "california_mission":
        return _site_place(site)
    return ""


def _short_name(page):
    """The name a child would type: the title without "Saint", "Mission", "Our Lady of" … in front."""
    title = re.sub(r"\s*\([^)]*\)", "", page.student_title or page.title)
    return re.sub(r"^(Saint|St\.|Mission|Our Lady of|The)\s+", "", title).strip()


def build_index(home):
    """[{t, k, s, p, w, i, u, m, n}]: title, group key, subtitle, place, words, intro sentence,
    url, map key (the World Discovery Map story to select, "" when it isn't on the map) and the
    short name used for the empty state's suggestions."""
    from .learning import LearningPage
    from .missions import MissionProjectsGuidePage
    from .models import FutureSaintsIndexPage
    from .worldmap import CALLOUT_KEY, WorldMapPage, world_items

    if home is None or not home.live:
        return []
    on_map = set()
    if WorldMapPage.objects.child_of(home).live().public().exists():
        on_map = {i["key"] for i in world_items(home, None)[0] if i["pinned"] or i["in_callout"]}
    callout = CALLOUT_KEY if CALLOUT_KEY in on_map else ""
    entries = []
    for page in LearningPage.objects.descendant_of(home).live().public().specific().prefetch_related("words"):
        place, url = _place(page), page.get_url(None)
        entries.append({
            "t": page.student_title or page.title, "k": page.content_kind, "s": page.subtitle, "p": place,
            "w": [w.word for w in page.words.all() if w.word], "i": first_sentence(page.intro), "u": url,
            "m": page.slug if page.slug in on_map else "", "n": _short_name(page),
        })
        project = page.published_project() if page.content_kind == "california_mission" else None
        if project is not None:
            entries.append({"t": project.project_title, "k": "project", "s": page.student_title or page.title,
                            "p": place, "w": [], "i": first_sentence(project.project_intro), "u": url + "#build",
                            "m": callout, "n": ""})
    hub = FutureSaintsIndexPage.objects.child_of(home).live().public().filter(content_kind="california_mission").first()
    if hub is not None:
        entries.append({"t": hub.hub_title or hub.title, "k": "california_mission", "s": hub.hub_subtitle,
                        "p": "California", "w": [], "i": first_sentence(hub.hub_intro or hub.intro),
                        "u": hub.get_url(None), "m": callout, "n": ""})
        guide = MissionProjectsGuidePage.objects.child_of(hub).live().public().first()
        if guide is not None:
            entries.append({"t": guide.title, "k": "california_mission", "s": "", "p": "California", "w": [],
                            "i": first_sentence(guide.intro), "u": guide.get_url(None), "m": callout, "n": ""})
    order = {k: n for n, (k, _) in enumerate(GROUPS)}
    entries.sort(key=lambda e: (order[e["k"]], fold(e["t"])))
    return entries


def search_index(home):
    """The cached index (rebuilt after INDEX_TTL or any publish/unpublish)."""
    data = cache.get(INDEX_CACHE_KEY)
    if data is None:
        data = build_index(home)
        cache.set(INDEX_CACHE_KEY, data, INDEX_TTL)
    return data


def clear_search_index(**kwargs):
    """page_published / page_unpublished handler (see FutureSaintsConfig.ready)."""
    cache.delete(INDEX_CACHE_KEY)
