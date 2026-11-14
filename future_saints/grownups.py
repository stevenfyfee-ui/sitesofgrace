"""Future Saints: "A Note for Grown-Ups" (/future-saints/for-grown-ups/).

The page's wording is the approved text in docs/future-saints/content/
future-saints-note-for-grown-ups.md, set in the template word for word (test_grown_ups checks it
against that file). Only its two placeholders are fields: [MAILING ADDRESS] and [EFFECTIVE DATE].
The page can be saved as a draft with either blank, but it can't be published (or submitted to
the review workflow, whose approval publishes it) until both are filled in: the edit form refuses
a submit, and future_saints/wagtail_hooks.py refuses a publish or bulk publish, keeping the draft.
"""
from django.db import models
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page

from .models import FutureSaintsGateMixin

# Edit-form actions that lead to the page going live: submitting to the workflow (its approval
# publishes the submitted revision) and acting on a workflow task from the edit view.
SUBMIT_ACTIONS = ("action-submit", "action-workflow-action", "action-restart-workflow")
REQUIRED_TO_PUBLISH = (("mailing_address", "Mailing address"), ("effective_date", "Effective date"))


def missing_fields(values):
    """The labels of the placeholder fields that are still blank."""
    return [label for name, label in REQUIRED_TO_PUBLISH if not str(values.get(name) or "").strip()]


class GrownUpsNotePageForm(WagtailAdminPageForm):
    def is_valid(self):
        valid = super().is_valid()
        if valid and any(action in self.data for action in SUBMIT_ACTIONS):
            for name, label in REQUIRED_TO_PUBLISH:
                if not str(self.cleaned_data.get(name) or "").strip():
                    self.add_error(name, f"{label} is required before this page goes to review or is published.")
                    valid = False
        return valid


class GrownUpsNotePage(FutureSaintsGateMixin, Page):
    mailing_address = models.TextField(
        blank=True, help_text="Fills [MAILING ADDRESS]. Required to publish. One line per line of the address.",
    )
    effective_date = models.DateField(null=True, blank=True, help_text="Fills [EFFECTIVE DATE]. Required to publish.")

    parent_page_types = ["future_saints.FutureSaintsHomePage"]
    subpage_types = []
    max_count = 1
    base_form_class = GrownUpsNotePageForm

    content_panels = Page.content_panels + [FieldPanel("mailing_address"), FieldPanel("effective_date")]

    class Meta:
        verbose_name = "Future Saints note for grown-ups"

    def get_template(self, request, *args, **kwargs):
        return "future_saints/grown_ups_page.html"

    def publish_problem(self):
        """Why this page can't be published yet, or "" if it can."""
        missing = missing_fields({name: getattr(self, name) for name, _ in REQUIRED_TO_PUBLISH})
        if missing:
            return (f"This page can't be published until these are filled in: {', '.join(missing)}. "
                    "Your changes were saved as a draft.")
        return ""
