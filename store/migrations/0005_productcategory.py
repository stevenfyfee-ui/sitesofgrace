import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0004_seed_own_brand_products"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, unique=True)),
                (
                    "slug",
                    models.SlugField(
                        blank=True,
                        help_text="Used in the ?category= link. Leave blank and it is generated from the name.",
                        max_length=60,
                        unique=True,
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True,
                        help_text="Optional internal note. Not shown on the site.",
                        max_length=200,
                    ),
                ),
                (
                    "sort_order",
                    models.IntegerField(
                        default=0, help_text="Lower numbers appear first in the filter row."
                    ),
                ),
                (
                    "live",
                    models.BooleanField(
                        default=True,
                        help_text="Uncheck to take this bucket and everything in it off the store page, without deleting anything.",
                    ),
                ),
            ],
            options={
                "verbose_name": "product category",
                "verbose_name_plural": "product categories",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddField(
            model_name="storeproduct",
            name="category_ref",
            field=models.ForeignKey(
                help_text="Which bucket this shows up under on the store page.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="store.productcategory",
            ),
        ),
        migrations.AlterField(
            model_name="storeproduct",
            name="live",
            field=models.BooleanField(
                default=True, help_text="Uncheck to take this off the store page."
            ),
        ),
    ]
