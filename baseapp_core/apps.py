from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp_core"
    label = "baseapp_core"
    verbose_name = "BaseApp Core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from .graphql.interfaces import interface_registry
        from .pghelpers import apply_pghistory_tracks
        from .plugins.registry import plugin_registry
        from .services.registry import service_registry

        plugin_registry.load_from_installed_apps()
        service_registry.load_from_installed_apps()
        interface_registry.load_from_installed_apps()

        # Apply all registered pghistory tracks
        apply_pghistory_tracks()
