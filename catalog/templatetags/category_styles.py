from django import template
from django.utils.html import json_script

from catalog.models import CATEGORY_STYLES, DEFAULT_CATEGORY_STYLE

register = template.Library()


@register.simple_tag
def category_styles_json(element_id="category-styles"):
    """<script type="application/json"> holding {"styles": ..., "default": ...}
    -- how map JS reads catalog.models.CATEGORY_STYLES instead of copying it."""
    return json_script({"styles": CATEGORY_STYLES, "default": DEFAULT_CATEGORY_STYLE}, element_id)
