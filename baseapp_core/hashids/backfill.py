import itertools
import uuid
from typing import TYPE_CHECKING, Any, Callable

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

if TYPE_CHECKING:
    from django.apps.registry import Apps

    from baseapp_core.hashids.models import PublicIdMapping


def get_models_with_public_id_mixin(apps: "Apps | None" = None) -> list[type[models.Model]]:
    from baseapp_core.hashids.models import PublicIdMixin

    if apps is None:
        apps = django_apps

    target_models = []
    all_models = apps.get_models()

    for model_class in all_models:
        try:
            if model_class._meta.abstract:
                continue

            if issubclass(model_class, PublicIdMixin):
                pk_field = model_class._meta.pk

                # Only process models with integer PKs (auto increment)
                if isinstance(pk_field, (models.AutoField, models.BigAutoField)):
                    target_models.append(model_class)

        except Exception:
            # Safety: some models may error during introspection; skip them
            continue

    return target_models


def backfill_model_mappings(
    model: type[models.Model],
    PublicIdMapping: type["PublicIdMapping"],
    batch_size: int = 1000,
    dry_run: bool = False,
    logger: Callable[[str], None] | None = None,
) -> int:
    def log(message: str) -> None:
        if logger:
            logger(message)

    pk_field = model._meta.pk
    app_label = model._meta.app_label
    model_name = model._meta.model_name

    # Verify this is a valid model for backfilling
    if not isinstance(pk_field, (models.AutoField, models.BigAutoField)):
        log(
            f"Skipping {app_label}.{model_name}: "
            f"primary key is not AutoField/BigAutoField ({pk_field})"
        )
        return 0

    ct = ContentType.objects.get_for_model(model)
    qs = model.objects.order_by(pk_field.name).values_list(pk_field.name, flat=True)

    created_count = 0
    batch_iter = iter(qs)

    while True:
        batch = list(itertools.islice(batch_iter, batch_size))
        if not batch:
            break

        # Find existing mappings for this batch
        existing_ids = set(
            PublicIdMapping.objects.filter(content_type=ct, object_id__in=batch).values_list(
                "object_id", flat=True
            )
        )
        missing = [obj_id for obj_id in batch if obj_id not in existing_ids]

        if missing:
            # Verify that the instances still exist before creating mappings
            # (they could have been deleted between the values_list query and now)
            verified_ids = set(
                model.objects.filter(pk__in=missing).values_list(pk_field.name, flat=True)
            )
            still_missing = [obj_id for obj_id in missing if obj_id in verified_ids]

            if not still_missing:
                log(
                    f"Skipped batch for {app_label}.{model_name} "
                    f"— all {len(missing)} IDs no longer exist"
                )
                continue

            to_create = [
                PublicIdMapping(public_id=uuid.uuid4(), content_type=ct, object_id=obj_id)
                for obj_id in still_missing
            ]

            if dry_run:
                log(
                    f"[DRY RUN] Would create {len(to_create)} mappings for "
                    f"{app_label}.{model_name} (batch)"
                )
            else:
                try:
                    with transaction.atomic():
                        PublicIdMapping.objects.bulk_create(
                            to_create, batch_size=batch_size, ignore_conflicts=True
                        )
                    created_count += len(to_create)
                except Exception as exc:
                    log(f"Partial failure creating batch for {app_label}.{model_name}: {exc}")

        log(
            f"Processed batch of {len(batch)} for {app_label}.{model_name} "
            f"— missing {len(missing)}"
        )

    log(f"Created {created_count} PublicIdMapping rows for {app_label}.{model_name}")
    return created_count


def backfill_all_models(
    apps: "Apps | None" = None,
    batch_size: int = 1000,
    dry_run: bool = False,
    logger: Callable[[str], None] | None = None,
    apps_filter: list[str] | None = None,
) -> int:
    from baseapp_core.hashids.models import PublicIdMapping as GlobalPublicIdMapping

    def log(message: str) -> None:
        if logger:
            logger(message)

    # Get the PublicIdMapping model (from apps registry if provided)
    if apps is not None:
        PublicIdMapping = apps.get_model("baseapp_core", "PublicIdMapping")
    else:
        PublicIdMapping = GlobalPublicIdMapping

    # Get all models with PublicIdMixin
    target_models = get_models_with_public_id_mixin(apps)

    # Apply apps filter if provided
    if apps_filter:
        target_models = [m for m in target_models if m._meta.app_label in apps_filter]

    if not target_models:
        log("No models found that inherit from PublicIdMixin.")
        return 0

    total_created = 0

    for model in target_models:
        created = backfill_model_mappings(
            model=model,
            PublicIdMapping=PublicIdMapping,
            batch_size=batch_size,
            dry_run=dry_run,
            logger=logger,
        )
        total_created += created

    log(f"Done — total mappings created: {total_created}")
    return total_created


def backfill_single_instance(
    app_label: str,
    model_name: str,
    pk: Any,
    dry_run: bool = False,
    logger: Callable[[str], None] | None = None,
) -> bool:
    from baseapp_core.hashids.models import PublicIdMapping, PublicIdMixin

    def log(message: str) -> None:
        if logger:
            logger(message)

    # Get the model class
    try:
        model = django_apps.get_model(app_label, model_name)
    except Exception as exc:
        log(f"Error getting model {app_label}.{model_name}: {exc}")
        return False

    # Validate model has PublicIdMixin
    if not issubclass(model, PublicIdMixin):
        log(f"Model {app_label}.{model_name} does not inherit from PublicIdMixin.")
        return False

    # Validate PK type
    pk_field = model._meta.pk
    if not isinstance(pk_field, (models.AutoField, models.BigAutoField)):
        log(
            f"Skipping {app_label}.{model_name}:{pk} - "
            f"primary key is not AutoField/BigAutoField ({pk_field})"
        )
        return False

    # Parse PK value
    try:
        if isinstance(pk_field, (models.AutoField, models.BigAutoField)):
            pk = int(pk)
        else:
            pk = pk_field.to_python(pk)
    except (ValueError, TypeError) as exc:
        log(
            f"Invalid pk value '{pk}' for {app_label}.{model_name} "
            f"(expected {pk_field.__class__.__name__}): {exc}"
        )
        return False

    # Check if instance exists
    if not model.objects.filter(pk=pk).exists():
        log(
            f"Instance {app_label}.{model_name}:{pk} does not exist in database. "
            f"Cannot create mapping."
        )
        return False

    # Check if mapping already exists
    ct = ContentType.objects.get_for_model(model)
    exists = PublicIdMapping.objects.filter(content_type=ct, object_id=pk).exists()

    if exists:
        log(f"PublicIdMapping already exists for {app_label}.{model_name}:{pk}")
        return False

    if dry_run:
        log(f"[DRY RUN] Would create mapping for {app_label}.{model_name}:{pk}")
        return True

    # Create the mapping
    try:
        m = PublicIdMapping.objects.create(public_id=uuid.uuid4(), content_type=ct, object_id=pk)
        log(f"Created mapping {m.public_id} for {app_label}.{model_name}:{pk}")
        return True
    except Exception as exc:
        log(f"Failed to create mapping for {app_label}.{model_name}:{pk}: {exc}")
        return False
