"""
The LegalPage publishing guard.

A LegalPage can always be saved as a draft, but it can't go live while its
body uses a {{TOKEN}} whose Legal details value is blank (or a token that
doesn't exist). Wagtail's before_publish_page hook runs after the edit or
create view has saved the new revision and before it publishes, so the
draft is kept and only the publish is refused. Bulk publishing from the
page listing gets the same check through before_bulk_action.
"""
from django.contrib import messages
from django.shortcuts import redirect
from wagtail import hooks

from home.models import LegalDetails, LegalPage


@hooks.register("before_publish_page")
def block_legal_page_publish(request, page):
    page = page.specific
    if not isinstance(page, LegalPage):
        return None
    problem = page.publish_problem(LegalDetails.load(request_or_site=request))
    if problem:
        messages.error(request, problem)
        return redirect("wagtailadmin_pages:edit", page.pk)
    return None


@hooks.register("before_bulk_action")
def block_legal_page_bulk_publish(request, action_type, objects, action_class_instance):
    if action_type != "publish":
        return None
    details = LegalDetails.load(request_or_site=request)
    blocked = [
        page.title
        for page in objects
        if isinstance(page.specific, LegalPage) and page.specific.publish_problem(details)
    ]
    if blocked:
        messages.error(
            request,
            "Not published: " + ", ".join(blocked) + " use Legal details that are still blank. "
            "Fill them in under Settings > Legal details, then publish again.",
        )
        # next_url is already checked against open redirects by Wagtail.
        return redirect(action_class_instance.next_url)
    return None
