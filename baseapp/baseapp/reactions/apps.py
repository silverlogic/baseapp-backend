from django.apps import AppConfig


class PackageConfig(AppConfig):
    default = True
    name = "baseapp.reactions"
    label = "baseapp_reactions"
    verbose_name = "BaseApp Reactions"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        """
        Prepare the Django application by importing signals module.
        
        This method is automatically called by Django when the application is fully loaded.
        It imports the signals module to ensure signal handlers are registered and connected.
        
        Note:
            The `# noqa` comment prevents linting tools from raising warnings about the import.
        """
        import baseapp.reactions.signals  # noqa
