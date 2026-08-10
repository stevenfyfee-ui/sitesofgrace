import calendar
from datetime import datetime, timedelta, timezone as dt_timezone

import feedparser
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone

from news.models import NewsItem, NewsSource

EXCERPT_LIMIT = 200

# Ordered so the first matching topic wins, per spec.
TOPIC_KEYWORDS = [
    ("shrines", ["shrine", "basilica", "sanctuary", "apparition", "eucharistic miracle", "cathedral", "grotto"]),
    ("events", ["festival", "procession", "rosary walk", "youth", "gathering", "novena", "feast day", "vigil"]),
    ("pilgrimage", ["pilgrim", "pilgrimage", "camino", "holy year", "jubilee"]),
    ("saints", ["canoniz", "beatif", "sainthood", "cause of", "venerable", "relic"]),
]


def strip_html(raw):
    return BeautifulSoup(raw or "", "html.parser").get_text(separator=" ", strip=True)


def truncate_excerpt(text, limit=EXCERPT_LIMIT):
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",.;:-") + "…"


def build_excerpt(entry):
    content = entry.get("content")
    raw = content[0].get("value", "") if content else entry.get("summary", "")
    return truncate_excerpt(strip_html(raw))


def assign_topic(title, summary):
    text = f"{title} {strip_html(summary)}".lower()
    for topic, keywords in TOPIC_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return topic
    return "general"


def extract_image_url(entry):
    for media_key in ("media_content", "media_thumbnail"):
        media = entry.get(media_key)
        if media and media[0].get("url"):
            return media[0]["url"]
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image/"):
            return link.get("href", "")
    return ""


def parse_published_at(entry):
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed_time:
        return timezone.now()
    return datetime.fromtimestamp(calendar.timegm(parsed_time), tz=dt_timezone.utc)


class Command(BaseCommand):
    help = "Fetch enabled NewsSource RSS feeds and upsert cached NewsItem rows."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=90)

        for source in NewsSource.objects.filter(enabled=True):
            added = updated = errors = 0
            try:
                parsed = feedparser.parse(source.feed_url)
                status = getattr(parsed, "status", None)
                if status and status >= 400:
                    raise RuntimeError(f"HTTP {status} fetching feed")
                if not parsed.entries:
                    exc = getattr(parsed, "bozo_exception", None)
                    raise RuntimeError(str(exc) if exc else "Feed returned no entries")

                for entry in parsed.entries:
                    guid = entry.get("id") or entry.get("link")
                    if not guid:
                        continue
                    title = (entry.get("title") or "").strip()
                    summary = entry.get("summary", "")
                    item, created = NewsItem.objects.update_or_create(
                        guid=guid,
                        defaults={
                            "source": source,
                            "title": title[:300],
                            "excerpt": build_excerpt(entry),
                            "link": entry.get("link") or "",
                            "published_at": parse_published_at(entry),
                            "image_url": extract_image_url(entry),
                            "topic": assign_topic(title, summary),
                        },
                    )
                    if created:
                        added += 1
                    else:
                        updated += 1

                source.last_fetched = timezone.now()
                source.last_error = ""
            except Exception as exc:
                errors += 1
                source.last_error = str(exc)[:500]

            source.save(update_fields=["last_fetched", "last_error"])
            self.stdout.write(f"{source.name}: added={added} updated={updated} errors={errors}")

        deleted, _ = NewsItem.objects.filter(published_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Pruned {deleted} item(s) older than 90 days"))
