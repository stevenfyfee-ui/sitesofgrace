"""Puts the store in the Wagtail sidebar as its own section.

Store
  |- Products            add / edit / delete, filter by category, kind, status
  |- Categories          add / rename / reorder / hide the buckets
  |- Waitlist signups    who asked to be told when a product ships
"""

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .models import ProductCategory, StoreProduct, WaitlistSignup


class StoreProductViewSet(SnippetViewSet):
    model = StoreProduct
    menu_label = "Products"
    icon = "tag"
    add_to_admin_menu = False
    list_display = [
        "admin_thumb",
        "title",
        "category",
        "kind",
        "price",
        "layout",
        "featured",
        "live",
    ]
    list_filter = ["category", "kind", "live", "featured", "layout"]
    search_fields = ["title", "subtitle", "description", "amazon_asin"]
    ordering = ["sort_order", "title"]
    list_per_page = 50


class ProductCategoryViewSet(SnippetViewSet):
    model = ProductCategory
    menu_label = "Categories"
    icon = "list-ul"
    add_to_admin_menu = False
    list_display = ["name", "slug", "sort_order", "live", "product_count"]
    list_filter = ["live"]
    search_fields = ["name", "slug"]
    ordering = ["sort_order", "name"]


class WaitlistSignupViewSet(SnippetViewSet):
    model = WaitlistSignup
    menu_label = "Waitlist signups"
    icon = "mail"
    add_to_admin_menu = False
    list_display = ["email", "product", "created_at"]
    list_filter = ["product"]
    search_fields = ["email"]
    ordering = ["-created_at"]
    list_per_page = 50


class StoreViewSetGroup(SnippetViewSetGroup):
    items = (StoreProductViewSet, ProductCategoryViewSet, WaitlistSignupViewSet)
    menu_label = "Store"
    menu_icon = "tag"
    menu_order = 300


register_snippet(StoreViewSetGroup)
