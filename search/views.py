from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import JsonResponse
from django.template.response import TemplateResponse

from catalog.models import (
    CATEGORY_CHOICES,
    CATEGORY_STYLES,
    DEFAULT_CATEGORY_STYLE,
    PilgrimageTrailPage,
    SacredSitePage,
    SaintPage,
)

# To enable logging of search queries for use with the "Promoted search results" module
# <https://docs.wagtail.org/en/stable/reference/contrib/searchpromotions.html>
# uncomment the following line and the lines indicated in the search function
# (after adding wagtail.contrib.search_promotions to INSTALLED_APPS):

# from wagtail.contrib.search_promotions.models import Query


# Single place a search group is declared -- suggest() and search() both read
# this list, so adding LearnPage later (deliberately out of scope for now) is
# one dictionary here and nothing else.
SEARCH_GROUPS = [
    {"key": "sites", "label": "Sacred Sites", "model": SacredSitePage},
    {"key": "saints", "label": "Saints", "model": SaintPage},
    {"key": "trails", "label": "Pilgrimage Trails", "model": PilgrimageTrailPage},
]

SUGGEST_PER_GROUP = 5
SUGGEST_RESULT_CAP = 50
PREVIEW_PER_GROUP = 10
RESULTS_PAGE_SIZE = 20


def _resolve(base_qs, q, cap):
    """autocomplete -> search -> icontains, stopping at the first step that
    returns anything. Always returns a plain list, capped at `cap` -- every
    caller immediately wants len() and/or a slice, never a lazy queryset.
    The icontains step is a safety net for the database backend's behaviour
    on very short or unusual fragments: an empty dropdown feels broken even
    when the backend is technically correct.
    """
    results = list(base_qs.autocomplete(q)[:cap])
    if results:
        return results
    results = list(base_qs.search(q)[:cap])
    if results:
        return results
    return list(base_qs.filter(title__icontains=q)[:cap])


def _site_meta(site):
    parts = [site.locality, site.country]
    return ", ".join(part for part in parts if part)


def _saint_meta(saint):
    return saint.feast_day or saint.honorific_type


def _trail_meta(trail):
    return trail.region or trail.country


_META_FNS = {"sites": _site_meta, "saints": _saint_meta, "trails": _trail_meta}


def _serialize_suggestion(group_key, obj):
    result = {
        "title": obj.title,
        "url": obj.url,
        "meta": _META_FNS[group_key](obj),
        "chip": None,
        "chip_fill": None,
        "chip_stroke": None,
        "chip_dot": None,
        "slug": None,
        "lat": None,
        "lng": None,
    }
    if group_key == "sites":
        style = CATEGORY_STYLES.get(obj.category, DEFAULT_CATEGORY_STYLE)
        result.update({
            "chip": obj.category,
            "chip_fill": style["fill"],
            "chip_stroke": style["stroke"],
            "chip_dot": style["dot"],
            "slug": obj.slug,
            "lat": float(obj.latitude) if obj.latitude is not None else None,
            "lng": float(obj.longitude) if obj.longitude is not None else None,
        })
    return result


def suggest(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"query": q, "groups": []})

    types_param = (request.GET.get("types") or "").strip()
    if types_param:
        wanted = {key.strip() for key in types_param.split(",") if key.strip()}
        groups = [group for group in SEARCH_GROUPS if group["key"] in wanted]
    else:
        groups = SEARCH_GROUPS

    response_groups = []
    for group in groups:
        # .public() is mandatory here: once the site goes behind page
        # privacy, a restricted page's title must never surface through
        # this endpoint.
        base_qs = group["model"].objects.live().public()
        matches = _resolve(base_qs, q, SUGGEST_RESULT_CAP)
        if not matches:
            continue
        response_groups.append({
            "key": group["key"],
            "label": group["label"],
            "total": len(matches),
            "results": [_serialize_suggestion(group["key"], obj) for obj in matches[:SUGGEST_PER_GROUP]],
        })

    response = JsonResponse({"query": q, "groups": response_groups})
    # No per-user data in this response -- but only because every query above
    # is .public(). If that guarantee is ever dropped, drop this header too.
    response["Cache-Control"] = "public, max-age=60"
    return response


def search(request):
    search_query = (request.GET.get("query") or "").strip()
    category_param = (request.GET.get("category") or "").strip()
    page_number = request.GET.get("page", 1)

    group_keys = {group["key"] for group in SEARCH_GROUPS}
    category_labels = dict(CATEGORY_CHOICES)

    active_group_key = None
    active_site_category = None
    if category_param in group_keys:
        active_group_key = category_param
    elif category_param in category_labels:
        active_group_key = "sites"
        active_site_category = category_param

    def _searched(qs):
        # SearchResults (what .search() returns) has no .filter() -- any
        # category narrowing has to happen on the plain PageQuerySet first.
        return qs.search(search_query) if search_query else qs.none()

    group_querysets = {
        group["key"]: _searched(group["model"].objects.live().public())
        for group in SEARCH_GROUPS
    }
    group_totals = {key: qs.count() for key, qs in group_querysets.items()}

    total_count = sum(group_totals.values())

    site_categories = []
    for value, label in CATEGORY_CHOICES:
        filtered_base = SacredSitePage.objects.live().public().filter(category=value)
        site_categories.append({
            "value": value,
            "label": label,
            "count": _searched(filtered_base).count(),
            "active": active_site_category == value,
        })

    groups = [
        {
            "key": group["key"],
            "label": group["label"],
            "total": group_totals[group["key"]],
            "active": active_group_key == group["key"] and active_site_category is None,
        }
        for group in SEARCH_GROUPS
    ]

    # Always show every group's and every category's full count -- computed
    # above regardless of which filter (if any) is active -- so the chip row
    # never has to hide or re-fetch counts when the reader switches filters.
    active_results = None
    groups_preview = None
    if active_group_key:
        if active_site_category:
            base = SacredSitePage.objects.live().public().filter(category=active_site_category)
            qs = _searched(base)
        else:
            qs = group_querysets[active_group_key]
        paginator = Paginator(qs, RESULTS_PAGE_SIZE)
        try:
            active_results = paginator.page(page_number)
        except PageNotAnInteger:
            active_results = paginator.page(1)
        except EmptyPage:
            active_results = paginator.page(paginator.num_pages or 1)
    else:
        groups_preview = [
            {
                "key": group["key"],
                "label": group["label"],
                "total": group_totals[group["key"]],
                "results": list(group_querysets[group["key"]][:PREVIEW_PER_GROUP]),
            }
            for group in SEARCH_GROUPS
        ]

    return TemplateResponse(
        request,
        "search/search.html",
        {
            "search_query": search_query,
            "groups": groups,
            "site_categories": site_categories,
            "active_category": category_param,
            "active_group_key": active_group_key,
            "active_site_category": active_site_category,
            "active_results": active_results,
            "groups_preview": groups_preview,
            "total_count": total_count,
        },
    )
