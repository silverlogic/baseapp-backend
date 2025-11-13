from __future__ import annotations

import itertools
import uuid
from typing import Iterable

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from baseapp_core.hashids.models import PublicIdMapping, PublicIdMixin


class Command(BaseCommand):
    help = "Backfill PublicIdMapping rows for existing model instances that use PublicIdMixin."

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

        # If an instance is specified, handle it directly and exit
        if instance_spec:
            try:
                model_path, pk_str = instance_spec.split(":", 1)
                app_label, model_name = model_path.split(".", 1)
                model = django_apps.get_model(app_label, model_name)
                pk = int(pk_str)
            except Exception as exc:  # pragma: no cover - input parsing
                self.stdout.write(self.style.ERROR(f"Invalid --instance format: {instance_spec}. Use app_label.Model:pk"))
                return

            if not issubclass(model, PublicIdMixin):
                self.stdout.write(
                    self.style.WARNING(f"Model {app_label}.{model_name} does not inherit from PublicIdMixin. Skipping.")
                )
                return

            pk_field = model._meta.pk
            if not isinstance(pk_field, (models.AutoField, models.BigAutoField)):
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {app_label}.{model_name}:{pk} - primary key is not AutoField/BigAutoField ({pk_field})"
                    )
                )
                return

            ct = ContentType.objects.get_for_model(model)
            exists = PublicIdMapping.objects.filter(content_type=ct, object_id=pk).exists()
            if exists:
                self.stdout.write(self.style.NOTICE(f"PublicIdMapping already exists for {app_label}.{model_name}:{pk}"))
                return

            if dry_run:
                self.stdout.write(self.style.NOTICE(f"[DRY RUN] Would create mapping for {app_label}.{model_name}:{pk}"))
                return

            try:
                m = PublicIdMapping.objects.create(public_id=uuid.uuid4(), content_type=ct, object_id=pk)
                self.stdout.write(self.style.SUCCESS(f"Created mapping {m.public_id} for {app_label}.{model_name}:{pk}"))
            except Exception as exc:  # pragma: no cover - runtime DB errors
                self.stdout.write(self.style.ERROR(f"Failed to create mapping for {app_label}.{model_name}:{pk}: {exc}"))
            return

        # Find all concrete models that inherit from PublicIdMixin
        all_models = django_apps.get_models()
        target_models = []
        for m in all_models:
            try:
                if m._meta.abstract:
                    continue
                if apps_filter and m._meta.app_label not in apps_filter:
                    continue
                if issubclass(m, PublicIdMixin):
                    target_models.append(m)
            except Exception:
                # safety: some models may error on import; skip them
                continue

        if not target_models:
            self.stdout.write(self.style.NOTICE("No models found that inherit from PublicIdMixin."))
            return

        total_created = 0
        for model in target_models:
            pk_field = model._meta.pk
            # Only sensible for integer PKs (auto increment).
            if not isinstance(pk_field, (models.AutoField, models.BigAutoField)):
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {model._meta.app_label}.{model._meta.model_name}: primary key is not AutoField/BigAutoField ({pk_field})"
                    )
                )
                continue

            ct = ContentType.objects.get_for_model(model)
            qs = model.objects.order_by(pk_field.name).values_list(pk_field.name, flat=True)

            created_for_model = 0
            batch_iter = iter(qs)
            while True:
                batch = list(itertools.islice(batch_iter, batch_size))
                if not batch:
                    break

                # find existing mappings for this batch
                existing_ids = set(
                    PublicIdMapping.objects.filter(content_type=ct, object_id__in=batch).values_list(
                        "object_id", flat=True
                    )
                )
                missing = [obj_id for obj_id in batch if obj_id not in existing_ids]

                if missing:
                    to_create = [
                        PublicIdMapping(public_id=uuid.uuid4(), content_type=ct, object_id=obj_id)
                        for obj_id in missing
                    ]

                    if dry_run:
                        self.stdout.write(
                            self.style.NOTICE(
                                f"[DRY RUN] Would create {len(to_create)} mappings for {model._meta.app_label}.{model._meta.model_name} (batch)"
                            )
                        )
                    else:
                        with transaction.atomic():
                            PublicIdMapping.objects.bulk_create(to_create, batch_size=batch_size)
                        created_for_model += len(to_create)

                # progress print
                self.stdout.write(
                    f"Processed batch of {len(batch)} for {model._meta.app_label}.{model._meta.model_name} — missing {len(missing)}"
                )

            total_created += created_for_model
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {created_for_model} PublicIdMapping rows for {model._meta.app_label}.{model._meta.model_name}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Done — total mappings created: {total_created}"))
