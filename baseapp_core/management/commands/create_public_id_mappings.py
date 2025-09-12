from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from baseapp_core.models import PublicIdMapping


class Command(BaseCommand):
    help = "Create public ID mappings for all existing model instances"

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            type=str,
            help='Specific app to process (e.g., "baseapp_auth")',
        )
        parser.add_argument(
            "--model",
            type=str,
            help='Specific model to process (e.g., "User")',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating mappings",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of objects to process in each batch (default: 1000)",
        )

    def handle(self, *args, **options):
        app_name = options.get("app")
        model_name = options.get("model")
        dry_run = options.get("dry_run", False)
        batch_size = options.get("batch_size", 1000)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No mappings will be created"))

        # Get all models that use PublicIdMixin
        models_to_process = []

        if app_name and model_name:
            # Process specific model
            try:
                model = apps.get_model(app_name, model_name)
                if hasattr(model, "public_id"):
                    models_to_process.append(model)
                else:
                    raise CommandError(f"Model {app_name}.{model_name} does not use PublicIdMixin")
            except LookupError:
                raise CommandError(f"Model {app_name}.{model_name} not found")
        elif app_name:
            # Process all models in specific app
            try:
                app_config = apps.get_app_config(app_name)
                for model in app_config.get_models():
                    if hasattr(model, "public_id"):
                        models_to_process.append(model)
            except LookupError:
                raise CommandError(f"App {app_name} not found")
        else:
            # Process all models that use PublicIdMixin
            for app_config in apps.get_app_configs():
                for model in app_config.get_models():
                    if hasattr(model, "public_id"):
                        models_to_process.append(model)

        if not models_to_process:
            self.stdout.write(self.style.WARNING("No models found that use PublicIdMixin"))
            return

        total_created = 0
        total_skipped = 0

        for model in models_to_process:
            self.stdout.write(f"Processing {model._meta.label}...")

            # Get all instances that don't have public ID mappings
            existing_mappings = PublicIdMapping.objects.filter(
                content_type__model=model._meta.model_name,
                content_type__app_label=model._meta.app_label,
            ).values_list("object_id", flat=True)

            instances = model.objects.exclude(pk__in=existing_mappings)
            total_instances = instances.count()

            if total_instances == 0:
                self.stdout.write("  All instances already have public ID mappings")
                continue

            self.stdout.write(f"  Found {total_instances} instances without public ID mappings")

            created_count = 0
            skipped_count = 0

            # Process in batches
            for i in range(0, total_instances, batch_size):
                batch = instances[i : i + batch_size]

                if not dry_run:
                    with transaction.atomic():
                        for instance in batch:
                            try:
                                # This will create the mapping
                                instance.public_id
                                created_count += 1
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(
                                        f"  Error creating mapping for {instance}: {e}"
                                    )
                                )
                                skipped_count += 1
                else:
                    created_count += len(batch)

                # Progress update
                processed = min(i + batch_size, total_instances)
                self.stdout.write(f"  Processed {processed}/{total_instances} instances")

            self.stdout.write(f"  Created {created_count} mappings, skipped {skipped_count}")

            total_created += created_count
            total_skipped += skipped_count

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed! Created {total_created} mappings, skipped {total_skipped}"
            )
        )
