from django.urls import reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.sidebar import LinkMenuItem
from wagtail.models import Site

from blog.models import BlogIndexPage


class BlogMenuItem(MenuItem):
    """Straight to the blog's page listing, where "Add child page" can only
    make a Blog post. Resolved per request, since the BlogIndexPage is made
    by an editor after deploy; until it exists this opens the Home page's
    listing instead, which is where it has to be created."""

    def render_component(self, request):
        # Menu item instances are shared between requests, so the URL is
        # handed straight to the component rather than stored on self.
        index_page = BlogIndexPage.objects.first()
        if index_page:
            url = reverse("wagtailadmin_explore", args=[index_page.pk])
        else:
            site = Site.find_for_request(request) or Site.objects.filter(is_default_site=True).first()
            url = (
                reverse("wagtailadmin_explore", args=[site.root_page_id])
                if site else reverse("wagtailadmin_explore_root")
            )
        return LinkMenuItem(
            self.name, self.label, url,
            icon_name=self.icon_name, classname=self.classname, attrs=self.attrs,
        )


@hooks.register("register_admin_menu_item")
def register_blog_menu_item():
    return BlogMenuItem("Blog", "", name="blog", icon_name="doc-full", order=110)
