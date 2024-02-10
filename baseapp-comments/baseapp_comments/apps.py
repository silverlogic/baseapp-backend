from django.apps import AppConfig


class CommentsConfig(AppConfig):
    default = True
    name = "baseapp_comments"
    verbose_name = "BaseApp Comments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import baseapp_comments.signals  # noqa
