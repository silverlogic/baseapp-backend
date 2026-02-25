from baseapp_core.plugins import BaseAppConfig


class PackageConfig(BaseAppConfig):
    name = "baseapp_pages"
    label = "baseapp_pages"
    verbose_name = "BaseApp Pages"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        super().ready()
        # TODO: If signals.py is deleted, remove this.
        import baseapp_pages.signals  # noqa
