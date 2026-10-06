"""Read the committed liturgical calendar files.

One file per civil year, written by `manage.py sync_liturgical_calendar`.
Nothing here touches the network: a year without a file simply has no
celebrations, and that is logged once per process rather than raised.
"""
import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"


def data_path(year):
    return DATA_DIR / f"litcal-US-{year}.json"


@lru_cache(maxsize=None)
def _warn_missing(year):
    # lru_cache makes this fire once per year per process.
    logger.warning("liturgy: no calendar file for %s (%s); run sync_liturgical_calendar", year, data_path(year))


@lru_cache(maxsize=16)
def _events_by_date(year):
    """{"YYYY-MM-DD": [event, ...]} for one year, highest grade first."""
    path = data_path(year)
    try:
        with open(path, encoding="utf-8") as fh:
            events = json.load(fh)["events"]
    except FileNotFoundError:
        _warn_missing(year)
        return {}
    except (OSError, ValueError, KeyError, TypeError):
        logger.exception("liturgy: unreadable calendar file %s", path)
        return {}
    by_date = {}
    for event in events:
        by_date.setdefault(event["date"], []).append(event)
    for day in by_date.values():
        # sort() is stable, so equal grades (two optional memorials) keep the
        # API's own order.
        day.sort(key=lambda event: -int(event.get("grade") or 0))
    return by_date


def celebrations_on(date):
    """Every celebration on `date`, highest grade first; [] if the year has no file."""
    return list(_events_by_date(date.year).get(date.isoformat(), []))


def season_on(date):
    """(season_key, season_label) for `date`, or ("", "") if unknown."""
    for event in celebrations_on(date):
        if event.get("liturgical_season"):
            return event["liturgical_season"], event.get("liturgical_season_lcl") or ""
    return "", ""
