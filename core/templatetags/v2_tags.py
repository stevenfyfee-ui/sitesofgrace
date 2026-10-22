from django import template

from core.v2 import v2_enabled as _v2_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def v2_enabled(context):
    """{% v2_enabled as v2 %} -- same answer as core.v2.v2_enabled(request)."""
    return _v2_enabled(context.get("request"))
