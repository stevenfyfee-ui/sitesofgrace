"""
The "A Note for Grown-Ups" publishing guard (the same pattern as home/wagtail_hooks.py).

The page can always be saved as a draft, but it can't go live while its mailing address or
effective date is blank. before_publish_page runs after the edit or create view has saved the new
revision and before it publishes, so the draft is kept and only the publish is refused. Bulk
publishing from the page listing gets the same check through before_bulk_action. Submitting to
the review workflow is refused by the page's edit form (future_saints.grownups).
"""
from django.contrib import messages
from django.shortcuts import redirect
from wagtail import hooks

from future_saints.grownups import GrownUpsNotePage


@hooks.register("before_publish_page")
def block_grown_ups_note_publish(request, page):
    page = page.specific
    if not isinstance(page, GrownUpsNotePage):
        return None
    problem = page.publish_problem()
    if problem:
        messages.error(request, problem)
        return redirect("wagtailadmin_pages:edit", page.pk)
    return None


@hooks.register("before_bulk_action")
def block_grown_ups_note_bulk_publish(request, action_type, objects, action_class_instance):
    if action_type != "publish":
        return None
    blocked = [page.title for page in objects
               if isinstance(page.specific, GrownUpsNotePage) and page.specific.publish_problem()]
    if blocked:
        messages.error(request, "Not published: " + ", ".join(blocked) + " still needs its mailing address "
                       "and effective date. Fill them in on the page, then publish again.")
        # next_url is already checked against open redirects by Wagtail.
        return redirect(action_class_instance.next_url)
    return None
