import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin

ReportType = swapper.load_model("baseapp_reports", "ReportType")
Report = swapper.load_model("baseapp_reports", "Report")


@admin.register(ReportType)
class ReportTypeAdmin(ModelAdmin):
    list_display = ("id", "key", "label", "parent_type")
    search_fields = ("key", "label")
    date_hierarchy = "created"


@admin.register(Report)
class ReportAdmin(ModelAdmin):
    list_display = ("id", "target", "user", "report_type", "report_subject", "created")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    raw_id_fields = ("user", "target_document")
    date_hierarchy = "created"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "report_type", "target_document__content_type")
            .prefetch_related("target_document__content_object")
        )
