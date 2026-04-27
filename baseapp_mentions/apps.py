from django.apps import AppConfig


class BaseappMentionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "baseapp_mentions"
    verbose_name = "Mentions"
