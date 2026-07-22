from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import NewsletterSignupForm
from .models import NewsletterSignup


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
