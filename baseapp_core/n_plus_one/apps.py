from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NPlusOneConfig(AppConfig):
    """N+1 reporting in dev (django-zeal). Opt-in: dev settings install it next to "zeal"."""

    name = "baseapp_core.n_plus_one"
    label = "baseapp_core_n_plus_one"
    verbose_name = _("N+1 detection")

    def ready(self) -> None:
        # Connected here rather than at import, so they exist only where the app is installed. A
        # Celery worker runs django.setup() before its first task, so it gets the task hooks too.
        from celery.signals import task_postrun, task_prerun
        from zeal.signals import nplusone_detected

        from . import end_zeal_context, log_n_plus_one, start_zeal_context

        nplusone_detected.connect(log_n_plus_one, dispatch_uid="baseapp_core.n_plus_one.log")
        task_prerun.connect(start_zeal_context, dispatch_uid="baseapp_core.n_plus_one.prerun")
        task_postrun.connect(end_zeal_context, dispatch_uid="baseapp_core.n_plus_one.postrun")
