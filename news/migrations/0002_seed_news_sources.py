from django.db import migrations

# Each URL was fetched with feedparser before this migration was written and
# confirmed to return valid, distinct RSS (see task notes) -- none are dead.
SOURCES = [
    {"name": "Vatican News", "feed_url": "https://www.vaticannews.va/en.rss.xml", "sort_order": 10},
    {"name": "EWTN News / CNA", "feed_url": "https://www.catholicnewsagency.com/rss/news.xml", "sort_order": 20},
    {"name": "National Catholic Register", "feed_url": "https://www.ncregister.com/feeds/general-news.xml", "sort_order": 30},
]


def seed_sources(apps, schema_editor):
    NewsSource = apps.get_model("news", "NewsSource")
    for entry in SOURCES:
        NewsSource.objects.get_or_create(
            feed_url=entry["feed_url"],
            defaults={"name": entry["name"], "sort_order": entry["sort_order"], "enabled": True},
        )


def unseed_sources(apps, schema_editor):
    NewsSource = apps.get_model("news", "NewsSource")
    NewsSource.objects.filter(feed_url__in=[s["feed_url"] for s in SOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_sources, unseed_sources),
    ]
