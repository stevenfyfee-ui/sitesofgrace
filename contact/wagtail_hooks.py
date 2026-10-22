"""
The "Messages" inbox: a Wagtail ModelViewSet over ContactMessage.

Superusers only. A future "Contact inbox" group would plug in at
SuperuserOnlyPolicy below -- e.g. also allow
user.groups.filter(name="Contact inbox").exists().

Messages are read here and never created here: everything on the edit
screen is read-only except the status and the staff note. Spam is hidden
from the list unless the status filter asks for it.
"""
from urllib.parse import quote

from django.urls import reverse
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import FieldPanel, HelpPanel, MultiFieldPanel
from wagtail.admin.ui.tables import Column, DateColumn, TitleColumn
from wagtail.admin.views.generic import IndexView
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.permission_policies import ModelPermissionPolicy

from .models import ContactMessage


class SuperuserOnlyPolicy(ModelPermissionPolicy):
    # Where a "Contact inbox" group would be allowed in later.
    def user_has_permission(self, user, action):
        if action == "add":
            return False
        return bool(user.is_active and user.is_superuser)

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, action) for action in actions)


class ReplyPanel(HelpPanel):
    """A "Reply by email" mailto link with the subject prefilled."""

    class BoundPanel(HelpPanel.BoundPanel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            message = self.instance
            if message and message.pk:
                subject = quote(f"Re: {message.get_topic_display()} (Sites of Grace)")
                self.content = format_html(
                    '<p><a class="button button-secondary" href="mailto:{}?subject={}">Reply by email</a></p>',
                    message.email, subject,
                )


class ContactMessageIndexView(IndexView):
    def get_base_queryset(self):
        queryset = super().get_base_queryset().select_related("related_page")
        if self.request.GET.get("status") != ContactMessage.STATUS_SPAM:
            queryset = queryset.exclude(status=ContactMessage.STATUS_SPAM)
        return queryset


class MessagesMenuItem(MenuItem):
    """The menu item, with the count of new messages in its label."""

    def __init__(self, *args, viewset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewset = viewset

    def is_shown(self, request):
        return self.viewset.permission_policy.user_has_permission(request.user, "change")

    def render_component(self, request):
        component = super().render_component(request)
        count = ContactMessage.objects.filter(status=ContactMessage.STATUS_NEW).count()
        if count:
            component.label = f"{self.label} ({count})"
        return component


class ContactMessageViewSet(ModelViewSet):
    model = ContactMessage
    name = "contact_messages"
    icon = "mail"
    menu_label = "Messages"
    menu_order = 250
    add_to_admin_menu = True
    copy_view_enabled = False
    inspect_view_enabled = False
    index_view_class = ContactMessageIndexView

    list_display = [
        DateColumn("created_at", label="Received", sort_key="created_at"),
        Column("topic", label="Topic", accessor="get_topic_display", sort_key="topic"),
        # The linked column that opens a message.
        TitleColumn(
            "name", label="Name", sort_key="name",
            get_url=lambda message: reverse("contact_messages:edit", args=[message.pk]),
        ),
        "email",
        Column("related_page", label="Related page", accessor="related_page"),
        Column("status", label="Status", accessor="get_status_display", sort_key="status"),
    ]
    list_filter = ["topic", "status"]
    search_fields = ["name", "email", "message"]
    # Plain database search: these rows never go into a search index.
    search_backend_name = None
    ordering = ["-created_at"]

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("created_at", read_only=True),
                FieldPanel("topic", read_only=True),
                FieldPanel("name", read_only=True),
                FieldPanel("email", read_only=True),
                FieldPanel("related_page", read_only=True),
                FieldPanel("user", read_only=True),
                FieldPanel("message", read_only=True),
                ReplyPanel(),
            ],
            heading="Message",
        ),
        MultiFieldPanel(
            [FieldPanel("status"), FieldPanel("staff_note")],
            heading="Follow-up",
        ),
    ]

    @property
    def permission_policy(self):
        return SuperuserOnlyPolicy(self.model)

    def get_menu_item(self, order=None):
        return MessagesMenuItem(
            label=self.menu_label,
            url=self.menu_url,
            name=self.menu_name,
            icon_name=self.menu_icon,
            order=order if order is not None else self.menu_order,
            viewset=self,
        )


@hooks.register("register_admin_viewset")
def register_contact_messages():
    return ContactMessageViewSet()
