from django.apps import AppConfig


class ContentFeedConfig(AppConfig):
    default = True
    name = "baseapp_content_feed"
    verbose_name = "BaseApp Content Feed"
    default_auto_field = "django.db.models.BigAutoField"
