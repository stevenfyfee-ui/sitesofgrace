from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import NewsletterSignupForm
from .models import NewsletterSignup


def health(request):
    # App Platform's rollout prober hits this before the app is warm and
    # before DATABASE_URL-backed connections are expected to work, so this
    # must never touch the database.
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    if getattr(settings, "SITE_PRIVATE", False):
        content = "User-agent: *\nDisallow: /\n"
    else:
        content = (
            "User-agent: *\nAllow: /\n\n"
            f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}\n"
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
    if form.is_valid():
        NewsletterSignup.objects.get_or_create(email=form.cleaned_data["email"])
        flag = "subscribed"
    else:
        flag = "newsletter_error"

    separator = "&" if "?" in next_url else "?"
    return HttpResponseRedirect(f"{next_url}{separator}{flag}=1")
