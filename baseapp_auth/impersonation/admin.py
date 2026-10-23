from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from .models import ImpersonationAction, ImpersonationSession
from .services import end_impersonation


class ImpersonationActionInline(admin.TabularInline):
    model = ImpersonationAction
    extra = 0
    can_delete = False
    fields = ("created", "method", "path", "operation_name", "status_code", "succeeded")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(ImpersonationSession)
class ImpersonationSessionAdmin(admin.ModelAdmin):
    """An audit trail: sessions can be revoked here but never edited."""

    list_display = (
        "id",
        "impersonator",
        "target",
        "read_only",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
    )
    list_filter = ("read_only", "end_reason")
    search_fields = ("impersonator__email", "target__email", "reason")
    raw_id_fields = ("impersonator", "target")
    readonly_fields = (
        "impersonator",
        "target",
        "reason",
        "read_only",
        "started_at",
        "expires_at",
        "ended_at",
        "end_reason",
        "ip",
        "user_agent",
    )
    inlines = [ImpersonationActionInline]
    actions = ["revoke_sessions"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    @admin.action(description=_("Revoke selected sessions"), permissions=["change"])
    def revoke_sessions(self, request: HttpRequest, queryset: QuerySet) -> None:
        for session in queryset.filter(ended_at__isnull=True):
            end_impersonation(session, ImpersonationSession.EndReason.REVOKED, request=request)
