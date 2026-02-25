from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_core"
    label = "baseapp_core"
    verbose_name = "BaseApp Core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .pghelpers import apply_pghistory_tracks

        # Apply all registered pghistory tracks
        apply_pghistory_tracks()
