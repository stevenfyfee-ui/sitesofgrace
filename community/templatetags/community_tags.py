from django import template

from community.models import JourneyEntry

register = template.Library()


@register.inclusion_tag("community/_journey_buttons.html", takes_context=True)
def journey_buttons(context, site):
    request = context["request"]
    current_status = None
    if request.user.is_authenticated:
        entry = JourneyEntry.objects.filter(user=request.user, site=site).first()
        current_status = entry.status if entry else None
    return {
        "site": site,
        "current_status": current_status,
        "is_authenticated": request.user.is_authenticated,
        "request": request,
    }
