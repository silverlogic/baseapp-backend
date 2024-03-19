import swapper
from django.contrib import admin

Report = swapper.load_model("baseapp_reports", "Report")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "target", "user", "report_type", "report_subject", "created")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    date_hierarchy = "created"
