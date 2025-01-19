from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp.reactions"
    label = "baseapp_reactions"
    verbose_name = "BaseApp Reactions"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        import baseapp.reactions.signals  # noqa
