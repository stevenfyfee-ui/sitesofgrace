from django.apps import AppConfig


class FutureSaintsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "future_saints"
    verbose_name = "Future Saints"

    def ready(self):
        from wagtail.signals import page_published, page_unpublished

        from catalog.models import SacredSitePage, SaintPage

        from . import models
        from .search import clear_search_index

        # Publishing or unpublishing any Future Saints page (or a canonical page whose place a
        # story shows) changes what search can find, so the cached index is dropped at once.
        senders = (models.FutureSaintsHomePage, models.FutureSaintsIndexPage, models.SaintLearningPage,
                   models.MarianLearningPage, models.EucharisticLearningPage, models.HolyLandLearningPage,
                   models.MissionLearningPage, models.MissionProjectsGuidePage, models.WorldMapPage,
                   SacredSitePage, SaintPage)
        for model in senders:
            page_published.connect(clear_search_index, sender=model, dispatch_uid=f"fs-search-pub-{model.__name__}")
            page_unpublished.connect(clear_search_index, sender=model, dispatch_uid=f"fs-search-unpub-{model.__name__}")
