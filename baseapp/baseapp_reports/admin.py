import swapper
from django.contrib import admin

ReportType = swapper.load_model("baseapp_reports", "ReportType")
Report = swapper.load_model("baseapp_reports", "Report")


@admin.register(ReportType)
class ReportTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "label", "parent_type")
    search_fields = ("key", "label")
    date_hierarchy = "created"


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "target", "user", "report_type", "report_subject", "created")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    date_hierarchy = "created"
