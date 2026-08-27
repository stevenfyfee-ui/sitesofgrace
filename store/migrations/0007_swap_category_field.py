from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0006_populate_product_categories"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="storeproduct",
            name="category",
        ),
        migrations.RenameField(
            model_name="storeproduct",
            old_name="category_ref",
            new_name="category",
        ),
    ]
