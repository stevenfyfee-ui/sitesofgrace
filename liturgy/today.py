"""Yesterday / today / tomorrow for the home page's "Today in the Church" card.

The date is taken from timezone.now() in settings.LITURGICAL_TIME_ZONE, never
from date.today() (the server's clock), so the card turns over at local
midnight wherever the server happens to run. Nothing is scheduled: every
request works out its own three days.
"""
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from catalog.text import fold

from .calendar import celebrations_on, season_on
from .feasts import load_index

logger = logging.getLogger(__name__)

# The card shows this many items per day before "+N more".
VISIBLE_ITEMS = 3
UPCOMING_WINDOW = 10
# Same rendition the Featured Sites and Saints bucket uses, so the card reuses
# renditions that already exist instead of generating new ones.
THUMB_SPEC = "fill-360x420"

# LitCal grade numbers, checked against litcal-US-2026.json:
#   0 weekday, 1 commemoration, 2 optional memorial, 3 memorial, 4 feast,
#   5 feast of the Lord (also every Sunday in Ordinary Time), 6 solemnity,
#   7 "celebration with precedence over solemnities" (the great solemnities,
#   but also the Sundays of Advent/Lent/Easter, Ash Wednesday, Holy Week and
#   the Easter octave).
GRADE_LABELS = {
    1: "Commemoration",
    2: "Optional Memorial",
    3: "Memorial",
    4: "Feast",
    5: "Feast",
    6: "Solemnity",
}
# The grade-7 rows that really are solemnities; the rest are Sundays and
# privileged weekdays, which carry no rank label.
GRADE7_SOLEMNITIES = {
    "Christmas", "Epiphany", "Easter", "Ascension", "Pentecost", "Trinity", "CorpusChristi",
}
# Grade 6 in the data, but a commemoration rather than a solemnity.
UNLABELLED_KEYS = {"AllSouls"}

COLOR_KEYS = {
    "white": "white", "red": "red", "green": "green", "purple": "violet",
    "violet": "violet", "rose": "rose", "gold": "gold",
}

# "[ US ] Blessed Marie Rose Durocher, Virgin" -> "Blessed Marie Rose Durocher, Virgin"
_REGION_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")
# Words a trailing ", Priest" / ", Bishop and Doctor of the Church" clause is
# made of. Only a clause built entirely from these is dropped before folding,
# so "Mary, Mother of God" keeps its "Mother of God".
TITLE_WORDS = {
    "abbot", "abbess", "and", "apostle", "apostles", "bishop", "bishops", "church", "companions",
    "deacon", "doctor", "doctors", "evangelist", "hermit", "martyr", "martyrs", "missionary",
    "monk", "of", "pope", "priest", "priests", "religious", "the", "virgin", "virgins", "widow",
}


def liturgical_date(now=None):
    tz = ZoneInfo(getattr(settings, "LITURGICAL_TIME_ZONE", "America/Los_Angeles"))
    now = now or timezone.now()
    if timezone.is_naive(now):
        now = now.replace(tzinfo=tz)
    return now.astimezone(tz).date()


def date_at_noon(day):
    """An aware datetime inside `day` in the liturgical time zone (for ?_date=)."""
    tz = ZoneInfo(getattr(settings, "LITURGICAL_TIME_ZONE", "America/Los_Angeles"))
    return datetime(day.year, day.month, day.day, 12, tzinfo=tz)


def weekday_label(day):
    return f"{day:%A}, {day:%B} {day.day}"


def short_label(day):
    return f"{day:%a}, {day:%b} {day.day}"


def display_name(name):
    return _REGION_TAG.sub("", name or "").strip()


def rank_label(event):
    grade = int(event.get("grade") or 0)
    key = event.get("event_key") or ""
    if key in UNLABELLED_KEYS:
        return ""
    if grade >= 7:
        return "Solemnity" if key in GRADE7_SOLEMNITIES else ""
    if grade == 5 and key.startswith("OrdSunday"):
        return ""
    return GRADE_LABELS.get(grade, "")


def fold_celebration(name):
    """fold() a celebration name the way our page titles fold.

    fold() already drops Saint / St. / Blessed; this also drops a trailing
    title clause such as ", Priest" or ", Bishop and Doctor of the Church".
    """
    name = display_name(name)
    head, sep, tail = name.partition(",")
    if sep and set(re.findall(r"[a-z]+", tail.lower())) <= TITLE_WORDS:
        name = head
    return fold(name)


def _color_key(event):
    """First vestment color of an event ("white", "violet", ...); white if unknown."""
    colors = event.get("color") or ["white"]
    return COLOR_KEYS.get(str(colors[0]).lower(), "white")


def _lead_event(events):
    """The celebration that sets the day's color.

    An optional memorial doesn't displace the day it falls on, so a green
    weekday with two optional memorials still reads as green.
    """
    for event in events:
        if int(event.get("grade") or 0) >= 3:
            return event
    for event in events:
        if int(event.get("grade") or 0) == 0:
            return event
    return events[0] if events else None


def _item(ref, meta=None):
    return {
        "title": ref["title"],
        "url": ref["url"],
        "kind": ref["kind"],
        "meta": meta or ref["meta"],
        "image_id": ref["image_id"],
        "thumbnail": None,
    }


def _items_for(day, events, index):
    """Our pages for one day, de-duplicated, in the order the card lists them."""
    days, titles = index["days"], index["titles"]
    seen, linked, saints, sites, anniversaries = set(), [], [], [], []

    def take(bucket, ref, meta=None):
        if ref["pk"] not in seen:
            seen.add(ref["pk"])
            bucket.append(_item(ref, meta))

    # A plain weekday ("Monday of the 29th Week of Ordinary Time") adds
    # nothing once a memorial or higher takes the day -- the season line
    # already names the season -- so it isn't listed then. It still counts
    # for the day's color and movable-feast matching, which use `events`.
    has_memorial = any(int(event.get("grade") or 0) >= 3 for event in events)

    celebrations = []
    for event in events:
        if has_memorial and int(event.get("grade") or 0) == 0:
            continue
        ref = titles.get(fold_celebration(event.get("name")))
        celebrations.append({
            "name": display_name(event.get("name")),
            "rank_label": rank_label(event),
            "color": _color_key(event),
            "page_url": ref["url"] if ref else None,
        })
        if ref:
            take(linked, ref)

    entries = list(days.get((day.month, day.day), []))
    for event in events:
        entries.extend(days.get(event.get("event_key"), []))
    for entry in entries:
        if entry["reason"] == "feast" and entry["kind"] == "saint":
            take(saints, entry["page"])
    for entry in entries:
        if entry["reason"] == "feast" and entry["kind"] == "site":
            take(sites, entry["page"])
    for entry in entries:
        if entry["reason"] == "anniversary":
            take(anniversaries, entry["page"], f"On this day in {entry['year']}")
    return celebrations, linked + saints + sites + anniversaries


def _day(day, index, with_upcoming=True):
    events = celebrations_on(day)
    season_key, season_label = season_on(day)
    lead = _lead_event(events)
    celebrations, items = _items_for(day, events, index)
    upcoming = None
    if with_upcoming and not items:
        for offset in range(1, UPCOMING_WINDOW + 1):
            ahead = day + timedelta(days=offset)
            _, ahead_items = _items_for(ahead, celebrations_on(ahead), index)
            if ahead_items:
                upcoming = {"date": ahead, "label": weekday_label(ahead), "item": ahead_items[0]}
                break
    return {
        "date": day,
        "iso": day.isoformat(),
        "label": weekday_label(day),
        "short_label": short_label(day),
        "season_key": season_key,
        "season": season_label,
        "color": _color_key(lead) if lead else "",
        "celebrations": celebrations,
        "items": items,
        "visible_items": items[:VISIBLE_ITEMS],
        "more_count": max(0, len(items) - VISIBLE_ITEMS),
        "upcoming": upcoming,
    }


def _attach_thumbnails(days):
    shown = []
    for day in days:
        shown.extend(day["visible_items"])
        if day["upcoming"]:
            shown.append(day["upcoming"]["item"])
    ids = {item["image_id"] for item in shown if item["image_id"]}
    if not ids:
        return
    from wagtail.images import get_image_model

    urls = {}
    for image in get_image_model().objects.filter(pk__in=ids).prefetch_renditions(THUMB_SPEC):
        try:
            urls[image.pk] = image.get_rendition(THUMB_SPEC).url
        except Exception:
            # A missing source file (common on a dev box) loses one thumbnail,
            # not the card.
            logger.warning("liturgy: no %s rendition for image %s", THUMB_SPEC, image.pk, exc_info=True)
    for item in shown:
        item["thumbnail"] = urls.get(item["image_id"])


def liturgical_today(now=None):
    """{"yesterday": Day, "today": Day, "tomorrow": Day}; `now` pins the clock in tests."""
    today = liturgical_date(now)
    index = load_index()
    days = {
        "yesterday": _day(today - timedelta(days=1), index),
        "today": _day(today, index),
        "tomorrow": _day(today + timedelta(days=1), index),
    }
    _attach_thumbnails(days.values())
    return days
