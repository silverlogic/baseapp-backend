import swapper
from django.contrib.auth.backends import BaseBackend

Report = swapper.load_model("baseapp_reports", "Report")

# No DB at import time (``ContentType.objects.get_for_model`` breaks pytest collection / early imports).
# Swapped ``Report`` uses the concrete model's ``app_label`` (e.g. ``reports``), matching ``auth_permission``.
VIEW_REPORT_PERMISSION = f"{Report._meta.app_label}.view_report"
ADD_REPORT_PERMISSION = f"{Report._meta.app_label}.add_report"


def user_can_list_reports_on_target(user, target):
    """Whether ``user`` may query the ``reports`` connection on this report target.

    Listing is gated by **global** ``view_report`` (same string as ``auth_permission`` /
    ``ModelBackend``), not object-level checks on ``target``. The ``target`` argument is
    kept for call-site clarity and future object-level rules.
    """
    return user.has_perm(VIEW_REPORT_PERMISSION)


class ReportsPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == ADD_REPORT_PERMISSION:
            return user_obj.is_authenticated

        if perm == VIEW_REPORT_PERMISSION and obj is not None:
            if user_obj.is_superuser:
                return True
            if isinstance(obj, Report) and user_obj.pk == obj.user_id:
                return True
            return False
