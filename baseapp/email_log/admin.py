import swapper
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from baseapp_core.admin_helpers import ModelAdmin

from .services import ResendError, resend
from .status import EmailLogStatus

EmailLog = swapper.load_model("baseapp_email_log", "EmailLog")


class StatusListFilter(admin.SimpleListFilter):
    """Filters on the unified status, which lives on djmail's message for email rows."""

    title = _("status")
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list:
        return EmailLogStatus.choices

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value():
            return queryset.with_status(self.value())
        return queryset


def _pre(value: str) -> str:
    # Escaped: a logged HTML body is shown as source, never rendered in the admin.
    return format_html('<pre style="white-space: pre-wrap">{}</pre>', value or "")


@admin.register(EmailLog)
class EmailLogAdmin(ModelAdmin):
    list_display = (
        "created",
        "channel",
        "subject",
        "to",
        "status_display",
        "sent_at",
        "category",
        "template",
    )
    list_filter = (StatusListFilter, "channel", "category", "created")
    list_select_related = ("message",)
    search_fields = (
        "message__subject",
        "message__to_email",
        "recipients",
        "cc",
        "bcc",
        "delivery_to",
        "related_label",
        "idempotency_key",
    )
    date_hierarchy = "created"
    actions = ("resend_emails",)

    fieldsets = (
        (
            _("Message"),
            {
                "fields": (
                    "channel",
                    "status_display",
                    "message_link",
                    "from_email",
                    "to",
                    "recipients",
                    "cc",
                    "bcc",
                    "reply_to",
                    "subject",
                    "body_text_display",
                    "body_html_display",
                    "attachments",
                    "sent_at",
                    "error_display",
                    "retry_count",
                )
            },
        ),
        (
            _("Metadata"),
            {
                "fields": (
                    "template",
                    "context",
                    "category",
                    "related_content_type",
                    "related_object_id",
                    "related_label",
                    "sent_by",
                    "resend_of",
                    "idempotency_key",
                    "created",
                    "modified",
                )
            },
        ),
    )

    def get_readonly_fields(self, request: HttpRequest, obj=None) -> list[str]:
        # A log is a record: every field, djmail's included, is read-only.
        return [field for fieldset in self.fieldsets for field in fieldset[1]["fields"]]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.display(description=_("status"))
    def status_display(self, obj: EmailLog) -> str:
        status = obj.status
        return EmailLogStatus(status).label if status else "-"

    @admin.display(description=_("djmail message"))
    def message_link(self, obj: EmailLog) -> str:
        if not obj.message_id:
            return "-"
        try:
            url = reverse("admin:djmail_message_change", args=[obj.message_id])
        except NoReverseMatch:
            return obj.message_id
        return format_html('<a href="{}">{}</a>', url, obj.message_id)

    @admin.display(description=_("body text"))
    def body_text_display(self, obj: EmailLog) -> str:
        return _pre(obj.body_text)

    @admin.display(description=_("body HTML"))
    def body_html_display(self, obj: EmailLog) -> str:
        return _pre(obj.body_html)

    @admin.display(description=_("error"))
    def error_display(self, obj: EmailLog) -> str:
        return _pre(obj.error)

    @admin.display(description=_("retries"))
    def retry_count(self, obj: EmailLog) -> str:
        # djmail starts at -1: the first failure is attempt 0.
        return str(obj.message.retry_count + 1) if obj.message_id else "-"

    @admin.action(description=_("Resend the selected emails"), permissions=["change"])
    def resend_emails(self, request: HttpRequest, queryset: QuerySet) -> None:
        resent = 0
        for log in queryset.select_related("message"):
            try:
                resend(log, sent_by=request.user)
            except ResendError as error:
                self.message_user(request, f"{log}: {error}", messages.WARNING)
            else:
                resent += 1
        if resent:
            self.message_user(
                request,
                ngettext("Resent %d email.", "Resent %d emails.", resent) % resent,
                messages.SUCCESS,
            )
