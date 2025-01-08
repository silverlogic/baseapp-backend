from django.apps import AppConfig


class ReactionsConfig(AppConfig):
    default = True
    name = "baseapp_reactions"
    verbose_name = "BaseApp Reactions"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        import baseapp_reactions.signals  # noqa
