import pytest
from django.contrib.contenttypes.models import ContentType

from baseapp_core.backfill import (
    backfill_all_models,
    backfill_model_document_ids,
    backfill_single_instance,
    get_models_with_document_id_mixin,
)
from baseapp_core.models import DocumentId
from testproject.testapp.models import DummyPublicIdModel
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


@pytest.mark.django_db
class TestGetModelsWithDocumentIdMixin:
    def test_returns_models_with_document_id_mixin(self):
        """Test that it returns models that inherit from DocumentIdMixin and have auto-increment PKs."""
        models = get_models_with_document_id_mixin()

        # Should include DummyPublicIdModel
        assert any(model.__name__ == "DummyPublicIdModel" for model in models)

        # All returned models should have DocumentIdMixin
        from baseapp_core.models import DocumentIdMixin

        for model in models:
            assert issubclass(model, DocumentIdMixin)

    def test_excludes_abstract_models(self):
        """Test that abstract models are not included."""
        models = get_models_with_document_id_mixin()

        for model in models:
            assert not model._meta.abstract

    def test_excludes_models_without_autoincrement_pk(self):
        """Test that models with UUID or other non-autoincrement PKs are excluded."""
        from django.db import models as django_models

        returned_models = get_models_with_document_id_mixin()

        for model in returned_models:
            pk_field = model._meta.pk
            # Should only have AutoField or BigAutoField
            assert isinstance(pk_field, (django_models.AutoField, django_models.BigAutoField))


@pytest.mark.django_db
class TestBackfillModelDocumentIds:
    @pytest.fixture
    def dummy_instances(self):
        """Create multiple dummy instances without document IDs."""
        # Clear any existing document IDs
        DocumentId.objects.all().delete()

        # Create instances (triggers will create document IDs)
        instances = [DummyPublicIdModelFactory() for _ in range(5)]

        # Delete document IDs to test backfill
        DocumentId.objects.filter(object_id__in=[i.pk for i in instances]).delete()

        return instances

    def test_creates_document_ids_for_model(self, dummy_instances):
        """Test that backfill creates document IDs for all instances of a model."""
        created_count = backfill_model_document_ids(
            model=DummyPublicIdModel,
            DocumentId=DocumentId,
            batch_size=10,
            dry_run=False,
        )

        assert created_count == len(dummy_instances)

        # Verify document IDs exist
        for instance in dummy_instances:
            assert DocumentId.objects.filter(
                object_id=instance.pk,
                content_type__model="dummypublicidmodel",
            ).exists()

    def test_dry_run_does_not_create_mappings(self, dummy_instances):
        """Test that dry_run mode doesn't actually create mappings."""
        created_count = backfill_model_document_ids(
            model=DummyPublicIdModel,
            DocumentId=DocumentId,
            batch_size=10,
            dry_run=True,
        )

        # Dry run returns 0 created
        assert created_count == 0

        # No document IDs should exist
        for instance in dummy_instances:
            assert not DocumentId.objects.filter(
                object_id=instance.pk,
                content_type__model="dummypublicidmodel",
            ).exists()

    def test_skips_existing_document_ids(self, dummy_instances):
        """Test that it doesn't recreate existing document IDs."""
        # Create document ID for first instance
        first_instance = dummy_instances[0]
        ct = ContentType.objects.get_for_model(first_instance.__class__)
        existing_doc_id = DocumentId.objects.create(content_type=ct, object_id=first_instance.pk)

        created_count = backfill_model_document_ids(
            model=DummyPublicIdModel,
            DocumentId=DocumentId,
            batch_size=10,
            dry_run=False,
        )

        # Should create only for remaining instances
        assert created_count == len(dummy_instances) - 1

        # Original document ID should be unchanged
        doc_id = DocumentId.objects.get(object_id=first_instance.pk)
        assert doc_id.public_id == existing_doc_id.public_id

    def test_batch_processing(self, dummy_instances):
        """Test that batch_size parameter works correctly."""
        created_count = backfill_model_document_ids(
            model=DummyPublicIdModel,
            DocumentId=DocumentId,
            batch_size=2,  # Small batch size
            dry_run=False,
        )

        assert created_count == len(dummy_instances)


@pytest.mark.django_db
class TestBackfillAllModels:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear mappings before each test."""
        DocumentId.objects.all().delete()

    def test_backfills_all_models_with_mixin(self):
        """Test that it backfills all models with DocumentIdMixin."""
        # Create instances
        instances = [DummyPublicIdModelFactory() for _ in range(3)]

        # Delete their mappings
        DocumentId.objects.filter(object_id__in=[i.pk for i in instances]).delete()

        total_created = backfill_all_models(
            apps=None,
            batch_size=10,
            dry_run=False,
            apps_filter=None,
        )

        # Should create at least the mappings for our test instances
        assert total_created >= len(instances)

    def test_apps_filter_limits_to_specific_apps(self):
        """Test that apps_filter parameter limits backfill to specific apps."""
        # Create test instances
        instances = [DummyPublicIdModelFactory() for _ in range(2)]

        # Delete mappings
        DocumentId.objects.filter(object_id__in=[i.pk for i in instances]).delete()

        # Backfill only testapp
        total_created = backfill_all_models(
            apps=None,
            batch_size=10,
            dry_run=False,
            apps_filter=["testapp"],
        )

        # Should have created mappings for testapp models
        assert total_created >= len(instances)

    def test_dry_run_returns_count_without_creating(self):
        """Test dry_run mode doesn't create mappings."""
        instances = [DummyPublicIdModelFactory() for _ in range(2)]

        # Delete mappings
        DocumentId.objects.filter(object_id__in=[i.pk for i in instances]).delete()

        total_created = backfill_all_models(
            apps=None,
            batch_size=10,
            dry_run=True,
            apps_filter=["testapp"],
        )

        # Dry run returns 0
        assert total_created == 0

        # No document IDs should be created
        for instance in instances:
            assert not DocumentId.objects.filter(object_id=instance.pk).exists()


@pytest.mark.django_db
class TestBackfillSingleInstance:
    @pytest.fixture
    def dummy_instance(self):
        """Create a dummy instance without mapping."""
        instance = DummyPublicIdModelFactory()
        DocumentId.objects.filter(object_id=instance.pk).delete()
        return instance

    def test_creates_document_id_for_single_instance(self, dummy_instance):
        """Test that it creates document ID for a specific instance."""
        success = backfill_single_instance(
            app_label="testapp",
            model_name="DummyPublicIdModel",
            pk=dummy_instance.pk,
            dry_run=False,
        )

        assert success is True

        # Verify document ID was created
        assert DocumentId.objects.filter(
            object_id=dummy_instance.pk,
            content_type__model="dummypublicidmodel",
        ).exists()

    def test_dry_run_does_not_create_document_id(self, dummy_instance):
        """Test dry_run mode for single instance."""
        success = backfill_single_instance(
            app_label="testapp",
            model_name="DummyPublicIdModel",
            pk=dummy_instance.pk,
            dry_run=True,
        )

        assert success is True

        # No document ID should be created
        assert not DocumentId.objects.filter(object_id=dummy_instance.pk).exists()

    def test_returns_false_for_nonexistent_instance(self):
        """Test that it returns False for instance that doesn't exist."""
        success = backfill_single_instance(
            app_label="testapp",
            model_name="DummyPublicIdModel",
            pk=99999,  # Non-existent PK
            dry_run=False,
        )

        assert success is False

    def test_returns_false_for_existing_mapping(self, dummy_instance):
        """Test that it returns False if mapping already exists."""
        # Create mapping first
        ct = ContentType.objects.get_for_model(dummy_instance.__class__)
        DocumentId.objects.create(content_type=ct, object_id=dummy_instance.pk)

        success = backfill_single_instance(
            app_label="testapp",
            model_name="DummyPublicIdModel",
            pk=dummy_instance.pk,
            dry_run=False,
        )

        assert success is False

    def test_returns_false_for_invalid_model(self):
        """Test that it returns False for invalid model name."""
        success = backfill_single_instance(
            app_label="testapp",
            model_name="NonExistentModel",
            pk=1,
            dry_run=False,
        )

        assert success is False

    def test_returns_false_for_model_without_document_id_mixin(self):
        """Test that it returns False for models that don't have DocumentIdMixin."""
        success = backfill_single_instance(
            app_label="contenttypes",
            model_name="ContentType",
            pk=1,
            dry_run=False,
        )

        assert success is False

    def test_handles_invalid_pk_format(self, dummy_instance):
        """Test that it handles invalid PK format gracefully."""
        success = backfill_single_instance(
            app_label="testapp",
            model_name="DummyPublicIdModel",
            pk="invalid_pk",  # Invalid format
            dry_run=False,
        )

        assert success is False
