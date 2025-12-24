from __future__ import annotations

from django.core.management.base import BaseCommand

from baseapp_core.backfill import backfill_all_models, backfill_single_instance


class Command(BaseCommand):
    help = "Backfill DocumentId rows for existing model instances that use DocumentIdMixin."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of object ids to process per DB query/bulk_create",
        )
        parser.add_argument(
            "--app",
            action="append",
            dest="apps",
            help="Limit to specific installed app labels (can be passed multiple times)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Don't write anything, just report what would be created",
        )
        parser.add_argument(
            "--instance",
            dest="instance",
            help="Backfill a single instance in the format app_label.Model:pk (example: users.User:1)",
        )

    def handle(self, *args, **options):
        batch_size: int = options["batch_size"]
        apps_filter: list | None = options.get("apps")
        dry_run: bool = options.get("dry_run", False)
        instance_spec: str | None = options.get("instance")

        # Handle single instance backfill
        if instance_spec:
            try:
                model_path, pk_str = instance_spec.split(":", 1)
                app_label, model_name = model_path.split(".", 1)
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Invalid --instance format: {instance_spec}. "
                        f"Use app_label.Model:pk (error: {exc})"
                    )
                )
                return

            success = backfill_single_instance(
                app_label=app_label,
                model_name=model_name,
                pk=pk_str,
                dry_run=dry_run,
            )

            if not success and not dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"No document ID was created for {app_label}.{model_name}:{pk_str}"
                    )
                )
            return

        # Handle bulk backfill
        total_created = backfill_all_models(
            apps=None,
            batch_size=batch_size,
            dry_run=dry_run,
            apps_filter=apps_filter,
        )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"[DRY RUN] Would have created {total_created} document IDs total"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backfill complete. Total document IDs created: {total_created}"
                )
            )
