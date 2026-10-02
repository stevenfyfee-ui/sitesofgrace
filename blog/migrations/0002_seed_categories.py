from django.db import migrations

CATEGORIES = [
    ("Sites", "sites", 10, "Stories and guides for the sacred places on the map."),
    ("Travel", "travel", 20, "Practical pilgrimage planning: getting there, where to stay, what to know."),
    ("Saints", "saints", 30, "The holy men and women connected to these places."),
    ("Other", "other", 90, "Reflections, updates, and everything else."),
]


def seed_categories(apps, schema_editor):
    BlogCategory = apps.get_model("blog", "BlogCategory")
    for name, slug, sort_order, description in CATEGORIES:
        BlogCategory.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "sort_order": sort_order, "description": description},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
