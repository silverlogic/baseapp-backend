import swapper
from django.contrib.auth.backends import BaseBackend

Report = swapper.load_model("baseapp_reports", "Report")


class ReportsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm in ["baseapp_reports.add_report"]:
            return user_obj.is_authenticated

        if perm == "baseapp_reports.view_report" and obj is not None:
            # Only users who has change permission can view unpublished reports
            if user_obj.id == obj.user_id:
                return True
            return user_obj.has_perm("baseapp_reports.view_report")
