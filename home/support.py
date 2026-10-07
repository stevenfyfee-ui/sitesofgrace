"""
Stripe Checkout for home.SupportPage -- amount parsing and the two Stripe
calls (create a Checkout Session, retrieve it on return).

Stripe hosts the whole payment page: no card data, email, or name ever
passes through this app, and nothing personal is sent to Stripe in
metadata. The API key is passed on each call (never set on the stripe
module), and is never logged or put in an exception message.
"""
import logging
import re
from decimal import Decimal

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)

# Shown on Stripe's checkout page, right above the pay button.
CHECKOUT_SUBMIT_MESSAGE = (
    "Sites of Grace is not a 501(c)(3) charitable organization. "
    "Contributions are voluntary and are not tax-deductible."
)

STRIPE_TIMEOUT_SECONDS = 10

# stripe-python has no per-call timeout; the legacy resource API
# (stripe.checkout.Session) reads it from this module-level HTTP client.
# Only the transport is shared -- the API key is still passed per call.
# Retries are off per call so one request is bounded by the timeout above,
# well inside gunicorn's worker timeout.
stripe.default_http_client = stripe.RequestsClient(timeout=STRIPE_TIMEOUT_SECONDS)

FREQUENCY_ONCE = "once"
FREQUENCY_MONTHLY = "monthly"

# Whole dollars and cents with at most two decimals. No signs, exponents,
# or thousands separators -- "1e3", "-5", and "1.005" all fail here.
_CUSTOM_AMOUNT_RE = re.compile(r"^\d{1,7}(\.\d{1,2})?$")

# Checkout Session ids are "cs_" + "test_"/"live_" + an opaque token.
_SESSION_ID_RE = re.compile(r"^cs_[A-Za-z0-9_]{8,200}$")


class StripeCallFailed(Exception):
    """A key-free stand-in for a stripe.StripeError, raised only to be logged."""


def log_stripe_error(message, exc):
    """logger.exception() for a Stripe failure, minus the original exception
    text: an AuthenticationError's message echoes a masked API key that
    keeps its last four characters. Type, status, code, and request id are
    what's needed to look the failure up in the Stripe dashboard.
    """
    detail = (
        f"{type(exc).__name__} http_status={getattr(exc, 'http_status', None)} "
        f"code={getattr(exc, 'code', None)} request_id={getattr(exc, 'request_id', None)}"
    )
    try:
        raise StripeCallFailed(detail) from None
    except StripeCallFailed:
        logger.exception(message)


class AmountError(ValueError):
    """The submitted amount can't be used. str(exc) is visitor-safe."""


def parse_presets(raw):
    """"5,10,25,50" -> [5, 10, 25, 50]. Raises ValueError on anything that
    isn't a comma-separated list of whole numbers."""
    parts = [part.strip() for part in str(raw or "").split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise ValueError("Enter whole-dollar amounts separated by commas, like 5,10,25,50.")
    return [int(part) for part in parts]


def amount_to_cents(page, choice, custom):
    """The visitor's choice as integer cents, validated against the page.

    `choice` is a preset value or "other"; a non-empty `custom` always
    wins, since with JavaScript off the "Other" box is always visible and a
    visitor may type into it without selecting "Other" first. (With JS on,
    the box is disabled unless "Other" is chosen, so it isn't submitted.)
    """
    custom = (custom or "").strip().lstrip("$").strip()
    if custom:
        if not _CUSTOM_AMOUNT_RE.match(custom):
            raise AmountError("Please enter an amount in dollars, like 15 or 7.50.")
        dollars = Decimal(custom)
    elif choice == "other":
        raise AmountError("Please enter an amount.")
    else:
        try:
            presets = parse_presets(page.preset_amounts)
        except ValueError:
            presets = []
        if not (choice or "").isdigit() or int(choice) not in presets:
            raise AmountError("Please choose an amount.")
        dollars = Decimal(int(choice))

    if not (Decimal(page.min_amount) <= dollars <= Decimal(page.max_amount)):
        raise AmountError(
            f"Please choose an amount from ${page.min_amount:,} to ${page.max_amount:,}."
        )
    return int(dollars * 100)


def format_cents(cents):
    """2500 -> "$25.00"."""
    return f"${Decimal(int(cents)) / 100:,.2f}"


def create_checkout_session(page_url, frequency, cents):
    """A Stripe Checkout Session for one contribution; returns its URL.

    Raises stripe.StripeError (including timeouts) on any failure.
    """
    monthly = frequency == FREQUENCY_MONTHLY
    price_data = {
        "currency": "usd",
        "product": settings.STRIPE_SUPPORT_PRODUCT_ID,
        "unit_amount": cents,
    }
    if monthly:
        price_data["recurring"] = {"interval": "month"}

    params = {
        "mode": "subscription" if monthly else "payment",
        "line_items": [{"price_data": price_data, "quantity": 1}],
        "success_url": page_url + "?thanks=1&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": page_url + "#give",
        "custom_text": {"submit": {"message": CHECKOUT_SUBMIT_MESSAGE}},
        # Nothing personal here, ever -- and no customer_email, even for a
        # signed-in pilgrim: Stripe collects it on its own page.
        "metadata": {"source": "support_page", "frequency": frequency},
    }
    if not monthly:
        params["submit_type"] = "pay"

    session = stripe.checkout.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        max_network_retries=0,
        **params,
    )
    return session.url


def completed_session_summary(session_id):
    """{"amount": "$25.00", "frequency": "one time"} for a completed
    Checkout Session, or None for a malformed id, an incomplete session, or
    any Stripe failure. Reads only the amount and mode -- never the email,
    name, or anything else the session holds.
    """
    if not _SESSION_ID_RE.match(session_id or ""):
        return None
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            api_key=settings.STRIPE_SECRET_KEY,
            max_network_retries=0,
        )
    except stripe.StripeError as exc:
        log_stripe_error("Couldn't retrieve a Stripe Checkout Session for the thank-you panel", exc)
        return None

    # Attribute access, not .get(): a StripeObject is not a dict (v8+).
    complete = getattr(session, "status", None) == "complete" or getattr(
        session, "payment_status", None
    ) in {"paid", "no_payment_required"}
    amount_total = getattr(session, "amount_total", None)
    if not complete or amount_total is None:
        return None
    return {
        "amount": format_cents(amount_total),
        "frequency": "monthly" if getattr(session, "mode", None) == "subscription" else "one time",
    }
