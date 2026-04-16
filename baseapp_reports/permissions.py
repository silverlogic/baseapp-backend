import swapper
from django.contrib.auth.backends import BaseBackend

Report = swapper.load_model("baseapp_reports", "Report")

VIEW_REPORT_PERMISSION = f"{Report._meta.app_label}.view_report"
ADD_REPORT_PERMISSION = f"{Report._meta.app_label}.add_report"


class ReportsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == ADD_REPORT_PERMISSION:
            return user_obj.is_authenticated

        if perm == VIEW_REPORT_PERMISSION and obj is not None:
            if user_obj.is_superuser:
                return True
            if isinstance(obj, Report) and user_obj.pk == obj.user_id:
                return True

            return user_obj.has_perm(VIEW_REPORT_PERMISSION)
