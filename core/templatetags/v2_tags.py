from django import template

from core.v2 import planner_v2_enabled as _planner_v2_enabled
from core.v2 import v2_enabled as _v2_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def v2_enabled(context):
    """{% v2_enabled as v2 %} -- same answer as core.v2.v2_enabled(request)."""
    return _v2_enabled(context.get("request"))


@register.simple_tag(takes_context=True)
def planner_v2_enabled(context):
    """{% planner_v2_enabled as planner_v2 %} -- core.v2.planner_v2_enabled(request)."""
    return _planner_v2_enabled(context.get("request"))
