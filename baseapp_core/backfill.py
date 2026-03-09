import itertools
import logging
import uuid
from typing import TYPE_CHECKING, Any

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from baseapp_core.utils import has_autoincrement_pk

if TYPE_CHECKING:
    from django.apps.registry import Apps

    from baseapp_core.models import DocumentId

logger = logging.getLogger(__name__)


class DocumentIdBackfiller:
    """Handles backfilling of DocumentId entries for models with DocumentIdMixin."""

    def __init__(
        self,
        apps: "Apps | None" = None,
        batch_size: int = 1000,
        dry_run: bool = False,
    ):
        self.apps = apps or django_apps
        self.batch_size = batch_size
        self.dry_run = dry_run

    def _get_document_id_model(self) -> type["DocumentId"]:
        """Get the DocumentId model from the apps registry."""
        from baseapp_core.models import DocumentId as GlobalDocumentId

        if self.apps is not django_apps:
            return self.apps.get_model("baseapp_core", "DocumentId")
        return GlobalDocumentId

    def _is_valid_model(self, model: type[models.Model]) -> bool:
        """Check if the model is valid for backfilling (has auto-increment PK)."""
        return has_autoincrement_pk(model)

    def get_models_with_document_id_mixin(self) -> list[type[models.Model]]:
        """Get all concrete models that inherit from DocumentIdMixin and have integer PKs."""
        from baseapp_core.models import DocumentIdMixin

        target_models = []
        all_models = self.apps.get_models()

        for model_class in all_models:
            try:
                if model_class._meta.abstract:
                    continue

                if issubclass(model_class, DocumentIdMixin) and self._is_valid_model(model_class):
                    target_models.append(model_class)

            except Exception:
                # Safety: some models may error during introspection; skip them
                continue

        return target_models

    def backfill_model(
        self,
        model: type[models.Model],
        DocumentId: type["DocumentId"] | None = None,
    ) -> int:
        """Backfill DocumentId entries for a specific model."""
        if DocumentId is None:
            DocumentId = self._get_document_id_model()

        pk_field = model._meta.pk
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        # Verify this is a valid model for backfilling
        if not self._is_valid_model(model):
            logger.warning(
                "Skipping %s.%s: does not have auto-increment primary key",
                app_label,
                model_name,
            )
            return 0

        ct = ContentType.objects.get_for_model(model)
        qs = model.objects.order_by(pk_field.name).values_list(pk_field.name, flat=True)

        created_count = 0
        batch_iter = iter(qs)

        while True:
            batch = list(itertools.islice(batch_iter, self.batch_size))
            if not batch:
                break

            # Find existing document IDs for this batch
            existing_ids = set(
                DocumentId.objects.filter(content_type=ct, object_id__in=batch).values_list(
                    "object_id", flat=True
                )
            )
            missing = [obj_id for obj_id in batch if obj_id not in existing_ids]

            if missing:
                # Verify that the instances still exist before creating document IDs
                # (they could have been deleted between the values_list query and now)
                verified_ids = set(
                    model.objects.filter(pk__in=missing).values_list(pk_field.name, flat=True)
                )
                still_missing = [obj_id for obj_id in missing if obj_id in verified_ids]

                if not still_missing:
                    logger.info(
                        "Skipped batch for %s.%s — all %d IDs no longer exist",
                        app_label,
                        model_name,
                        len(missing),
                    )
                    continue

                to_create = [
                    DocumentId(public_id=uuid.uuid4(), content_type=ct, object_id=obj_id)
                    for obj_id in still_missing
                ]

                if self.dry_run:
                    logger.info(
                        "[DRY RUN] Would create %d document IDs for %s.%s (batch)",
                        len(to_create),
                        app_label,
                        model_name,
                    )
                else:
                    try:
                        with transaction.atomic():
                            DocumentId.objects.bulk_create(
                                to_create, batch_size=self.batch_size, ignore_conflicts=True
                            )
                        created_count += len(to_create)
                    except Exception as exc:
                        logger.error(
                            "Partial failure creating batch for %s.%s: %s",
                            app_label,
                            model_name,
                            exc,
                            exc_info=True,
                        )

            logger.debug(
                "Processed batch of %d for %s.%s — missing %d",
                len(batch),
                app_label,
                model_name,
                len(missing),
            )

        logger.info("Created %d DocumentId rows for %s.%s", created_count, app_label, model_name)
        return created_count

    def backfill_all_models(self, apps_filter: list[str] | None = None) -> int:
        """Backfill DocumentId entries for all models with DocumentIdMixin."""
        DocumentId = self._get_document_id_model()

        # Get all models with DocumentIdMixin
        target_models = self.get_models_with_document_id_mixin()

        # Apply apps filter if provided
        if apps_filter:
            target_models = [m for m in target_models if m._meta.app_label in apps_filter]

        if not target_models:
            logger.warning("No models found that inherit from DocumentIdMixin.")
            return 0

        total_created = 0

        for model in target_models:
            created = self.backfill_model(model=model, DocumentId=DocumentId)
            total_created += created

        logger.info("Done — total document IDs created: %d", total_created)
        return total_created

    def backfill_single_instance(self, app_label: str, model_name: str, pk: Any) -> bool:
        """Backfill DocumentId for a single model instance."""
        from baseapp_core.models import DocumentId, DocumentIdMixin

        # Get the model class
        try:
            model = self.apps.get_model(app_label, model_name)
        except Exception as exc:
            logger.error("Error getting model %s.%s: %s", app_label, model_name, exc)
            return False

        # Validate model has DocumentIdMixin
        if not issubclass(model, DocumentIdMixin):
            logger.error("Model %s.%s does not inherit from DocumentIdMixin", app_label, model_name)
            return False

        # Validate model has auto-increment PK
        if not self._is_valid_model(model):
            logger.warning(
                "Skipping %s.%s:%s - does not have auto-increment primary key",
                app_label,
                model_name,
                pk,
            )
            return False

        try:
            pk = int(pk)
        except (ValueError, TypeError) as exc:
            logger.error(
                "Invalid pk value '%s' for %s.%s (expected integer): %s",
                pk,
                app_label,
                model_name,
                exc,
            )
            return False

        # Check if instance exists
        if not model.objects.filter(pk=pk).exists():
            logger.error(
                "Instance %s.%s:%s does not exist in database. Cannot create mapping.",
                app_label,
                model_name,
                pk,
            )
            return False

        # Check if document ID already exists
        ct = ContentType.objects.get_for_model(model)
        exists = DocumentId.objects.filter(content_type=ct, object_id=pk).exists()

        if exists:
            logger.info("DocumentId already exists for %s.%s:%s", app_label, model_name, pk)
            return False

        if self.dry_run:
            logger.info(
                "[DRY RUN] Would create document ID for %s.%s:%s", app_label, model_name, pk
            )
            return True

        # Create the document ID
        try:
            m = DocumentId.objects.create(public_id=uuid.uuid4(), content_type=ct, object_id=pk)
            logger.info(
                "Created document ID %s for %s.%s:%s", m.public_id, app_label, model_name, pk
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to create document ID for %s.%s:%s: %s",
                app_label,
                model_name,
                pk,
                exc,
                exc_info=True,
            )
            return False


def get_models_with_document_id_mixin(apps: "Apps | None" = None) -> list[type[models.Model]]:
    """Get all concrete models that inherit from DocumentIdMixin and have integer PKs."""
    backfiller = DocumentIdBackfiller(apps=apps)
    return backfiller.get_models_with_document_id_mixin()


def backfill_model_document_ids(
    model: type[models.Model],
    DocumentId: type["DocumentId"],
    batch_size: int = 1000,
    dry_run: bool = False,
) -> int:
    """Backfill DocumentId entries for a specific model."""
    backfiller = DocumentIdBackfiller(batch_size=batch_size, dry_run=dry_run)
    return backfiller.backfill_model(model=model, DocumentId=DocumentId)


def backfill_all_models(
    apps: "Apps | None" = None,
    batch_size: int = 1000,
    dry_run: bool = False,
    apps_filter: list[str] | None = None,
) -> int:
    """Backfill DocumentId entries for all models with DocumentIdMixin."""
    backfiller = DocumentIdBackfiller(apps=apps, batch_size=batch_size, dry_run=dry_run)
    return backfiller.backfill_all_models(apps_filter=apps_filter)


def backfill_single_instance(
    app_label: str,
    model_name: str,
    pk: Any,
    dry_run: bool = False,
) -> bool:
    """Backfill DocumentId for a single model instance."""
    backfiller = DocumentIdBackfiller(dry_run=dry_run)
    return backfiller.backfill_single_instance(app_label=app_label, model_name=model_name, pk=pk)
