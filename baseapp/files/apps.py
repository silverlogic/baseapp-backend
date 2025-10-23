from django.apps import AppConfig


class FilesConfig(AppConfig):
    name = "baseapp.files"
    label = "baseapp_files"
    verbose_name = "BaseApp Files"

    def ready(self):
        import baseapp.files.signals  # noqa
