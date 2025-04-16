from django.apps import apps
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from baseapp_wagtail.settings import (
    WAGTAIL_INSTALLED_APPS,
    WAGTAIL_INSTALLED_INTERNAL_APPS,
)


class Command(BaseCommand):
    help = "Reverts all migrations for the Wagtail package apps"

    def handle(self, *args, **options):
        if not options.get("no_input", False):
            self.stdout.write(
                self.style.WARNING(
                    "This will delete all Wagtail-related data. "
                    "Make sure you have backed up your database.\n"
                    "Are you sure you want to proceed? [y/N]"
                )
            )
            if input("").lower() != "y":
                self.stdout.write("Operation cancelled.")
                return

        for app in [*WAGTAIL_INSTALLED_INTERNAL_APPS, *WAGTAIL_INSTALLED_APPS]:
            try:
                with transaction.atomic():
                    app_label = self._get_app_label(app)
                    self._remove_permissions(app_label)
                    call_command("migrate", app_label, "zero")
                    self.stdout.write(
                        self.style.SUCCESS(f"Reverted migrations for {app} ({app_label})")
                    )
            except CommandError as e:
                self.stdout.write(self.style.ERROR(f"Failed to revert migrations for {app}: {e}"))

    def _get_app_label(self, app_name):
        all_apps = apps.get_app_configs()
        for app_config in all_apps:
            if app_config.name == app_name:
                return app_config.label
        raise CommandError(f"App with name {app_name} not found")

    def _remove_permissions(self, app_label):
        """
        Some apps use django.contrib.auth.models.Permission to manage permissions. To revert their
        migrations, we need to remove the permissions first.
        """
        try:
            Permission.objects.filter(content_type__app_label=app_label).delete()
            self.stdout.write(self.style.SUCCESS(f"Removed permissions for {app_label}"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to remove permissions for {app_label}: {e}")
            )
