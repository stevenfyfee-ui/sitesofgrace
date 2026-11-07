"""Shared test helpers."""
from wagtail.models import Site


def use_only_default_site(testcase, **fields):
    """Create the test's Site as the only default Site, and keep Wagtail's
    site-root-paths cache from outliving the test's rollback.

    Both problems made results depend on test order:
    - beside the migration's default Site, a second default makes a request
      for an unknown host pick one in no fixed row order (a 404 sometimes);
    - Wagtail caches site root paths outside the test transaction, so a
      cached path for a rolled-back Site sends a later test's page lookups
      to a Site that no longer exists (Site.DoesNotExist, or a 404).
    """
    Site.clear_site_root_paths_cache()
    testcase.addCleanup(Site.clear_site_root_paths_cache)
    Site.objects.update(is_default_site=False)
    return Site.objects.create(is_default_site=True, **fields)
