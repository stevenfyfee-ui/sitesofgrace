from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core import ratelimit
from pilgrims.views import _ip_hash

from .forms import WaitlistSignupForm
from .models import StoreProduct, WaitlistSignup

# Per hashed IP, same limiter as Support checkout (core/ratelimit.py).
WAITLIST_LIMIT = 5
WAITLIST_WINDOW_SECONDS = 10 * 60


@require_POST
def waitlist_signup(request):
    next_url = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"

    form = WaitlistSignupForm(request.POST)
    product = None
    if ratelimit.hit("waitlist", _ip_hash(request), WAITLIST_LIMIT, WAITLIST_WINDOW_SECONDS):
        separator = "&" if "?" in next_url else "?"
        product_id = request.POST.get("product_id", "")
        return HttpResponseRedirect(f"{next_url}{separator}waitlist_error=rate&product_id={product_id}")
    if form.is_valid():
        product = StoreProduct.objects.filter(pk=form.cleaned_data["product_id"]).first()

    if product:
        WaitlistSignup.objects.get_or_create(product=product, email=form.cleaned_data["email"])
        flag = "waitlisted"
        product_id = product.pk
    else:
        flag = "waitlist_error"
        product_id = request.POST.get("product_id", "")

    separator = "&" if "?" in next_url else "?"
    return HttpResponseRedirect(f"{next_url}{separator}{flag}=1&product_id={product_id}")
