from django.apps import AppConfig


class ToursConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tours"
    verbose_name = "Guided pilgrimages"

    def ready(self):
        from . import signals  # noqa: F401
