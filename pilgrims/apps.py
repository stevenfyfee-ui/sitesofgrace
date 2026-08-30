from django.apps import AppConfig


class PilgrimsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pilgrims"
    verbose_name = "Pilgrim Portal"

    def ready(self):
        from . import signals  # noqa: F401
