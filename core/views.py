from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from wagtail.models import Site

from pilgrims.views import _ip_hash

from . import ratelimit
from .forms import NewsletterSignupForm
from .models import NewsletterSignup

# Per hashed IP, same limiter as Support checkout (core/ratelimit.py).
NEWSLETTER_LIMIT = 5
NEWSLETTER_WINDOW_SECONDS = 10 * 60


def health(request):
    # App Platform's rollout prober hits this before the app is warm and
    # before DATABASE_URL-backed connections are expected to work, so this
    # must never touch the database.
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    if getattr(settings, "SITE_NOINDEX", False):
        content = "User-agent: *\nDisallow: /\n"
    else:
        # The Wagtail Site's root URL, as the sitemap's own links use, so a
        # request on the app's ondigitalocean.app address still points
        # crawlers at the canonical https://sitesofgrace.com/sitemap.xml.
        site = Site.find_for_request(request)
        root = site.root_url if site else request.build_absolute_uri("/").rstrip("/")
        content = (
            "User-agent: *\nAllow: /\n\n"
            f"Sitemap: {root}/sitemap.xml\n"
        )
    return HttpResponse(content, content_type="text/plain")


@require_POST
def newsletter_signup(request):
    next_url = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"

    form = NewsletterSignupForm(request.POST)
    if ratelimit.hit("newsletter", _ip_hash(request), NEWSLETTER_LIMIT, NEWSLETTER_WINDOW_SECONDS):
        separator = "&" if "?" in next_url else "?"
        return HttpResponseRedirect(f"{next_url}{separator}newsletter_error=rate")
    if form.is_valid():
        NewsletterSignup.objects.get_or_create(email=form.cleaned_data["email"])
        flag = "subscribed"
    else:
        flag = "newsletter_error"

    separator = "&" if "?" in next_url else "?"
    return HttpResponseRedirect(f"{next_url}{separator}{flag}=1")
