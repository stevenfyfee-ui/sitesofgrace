"""StreamField launch-copy defaults are callables, so they can't be mutated.

Wagtail adds block ids to a default's dicts in place. With a shared literal
default that leaked into the field definition, so makemigrations --check
(blog.tests.MigrationStateTests) failed whenever these pages were built by an
earlier test, and new pages in one process reused the same block ids.
"""
from django.test import TestCase

from home.models import AboutPage, ContactPage, SupportPage

FIELDS = (
    (AboutPage, "pillars"),
    (AboutPage, "becoming_cards"),
    (SupportPage, "helps"),
    (SupportPage, "faqs"),
    (ContactPage, "topic_cards"),
    (ContactPage, "faqs"),
)


class StreamFieldDefaultTests(TestCase):
    def test_each_page_gets_its_own_default(self):
        for model, name in FIELDS:
            field = model._meta.get_field(name)
            self.assertTrue(callable(field.default), f"{model.__name__}.{name}")
            self.assertIsNot(field.default(), field.default())

    def test_saving_the_default_leaves_the_field_definition_alone(self):
        for model, name in FIELDS:
            field = model._meta.get_field(name)
            before = field.deconstruct()
            # get_prep_value is what saving does: it gives every block an id.
            first = field.get_prep_value(getattr(model(title="One"), name))
            second = field.get_prep_value(getattr(model(title="Two"), name))
            self.assertEqual(field.deconstruct(), before, f"{model.__name__}.{name}")
            ids_first, ids_second = {b["id"] for b in first}, {b["id"] for b in second}
            self.assertTrue(all(ids_first) and all(ids_second))
            self.assertFalse(ids_first & ids_second, f"{model.__name__}.{name}: block ids shared")
