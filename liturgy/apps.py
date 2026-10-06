from django.apps import AppConfig


class LiturgyConfig(AppConfig):
    """The liturgical calendar behind the home page's "Today in the Church" card.

    No models: the calendar is committed JSON under liturgy/data/, and the
    saints and sites it points at are catalog pages.
    """

    name = "liturgy"
    verbose_name = "Liturgical calendar"

    def ready(self):
        from wagtail.signals import page_published, page_unpublished

        from catalog.models import SacredSitePage, SaintPage

        from .feasts import clear_day_index

        # Publishing or unpublishing a saint or site changes which pages a
        # day can show, so the cached index is dropped right away instead of
        # waiting out its 15 minutes.
        for model in (SaintPage, SacredSitePage):
            page_published.connect(clear_day_index, sender=model, dispatch_uid=f"liturgy-pub-{model.__name__}")
            page_unpublished.connect(clear_day_index, sender=model, dispatch_uid=f"liturgy-unpub-{model.__name__}")
