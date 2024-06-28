from django.apps import AppConfig


class RatingsConfig(AppConfig):
    default = True
    name = "baseapp_ratings"
    verbose_name = "BaseApp Ratings"
    default_auto_field = "django.db.models.AutoField"
