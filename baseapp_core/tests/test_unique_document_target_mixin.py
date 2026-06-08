import pytest

from baseapp_core.models import DocumentId
from testproject.testapp.models import DummyPublicIdModel, DummyUniqueDocumentTarget
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


@pytest.mark.django_db
class TestDocumentIdUniqueTargetMixin:
    @pytest.fixture
    def dummy_instance(self, db):
        return DummyPublicIdModelFactory()

    def test_target_is_one_to_one_primary_key_to_document_id(self):
        target_field = DummyUniqueDocumentTarget._meta.get_field("target")
        assert target_field.one_to_one is True
        assert target_field.primary_key is True
        assert target_field.related_model is DocumentId

    def test_related_name_is_app_label_and_class_scoped(self, dummy_instance):
        metadata = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)
        # related_name="%(app_label)s_%(class)s" keeps the reverse accessor unique per model.
        assert metadata.target.testapp_dummyuniquedocumenttarget == metadata

    def test_get_or_create_for_object_creates_row_and_document_id(self, dummy_instance):
        metadata = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)

        assert metadata is not None
        assert metadata.target.content_object == dummy_instance
        assert DocumentId.objects.filter(pk=metadata.target_id).exists()

    def test_get_or_create_for_object_is_idempotent(self, dummy_instance):
        first = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)
        second = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)

        assert first.pk == second.pk
        assert DummyUniqueDocumentTarget.objects.count() == 1

    def test_get_or_create_for_object_returns_none_for_falsy_object(self):
        assert DummyUniqueDocumentTarget.get_or_create_for_object(None) is None

    def test_get_or_create_for_object_returns_none_for_unsaved_object(self):
        unsaved = DummyPublicIdModel(name="unsaved")
        assert unsaved.pk is None
        assert DummyUniqueDocumentTarget.get_or_create_for_object(unsaved) is None

    def test_get_for_object_returns_existing_row(self, dummy_instance):
        created = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)
        assert DummyUniqueDocumentTarget.get_for_object(dummy_instance) == created

    def test_get_for_object_returns_none_when_missing(self, dummy_instance):
        assert DummyUniqueDocumentTarget.get_for_object(dummy_instance) is None

    def test_get_for_object_returns_none_for_falsy_object(self):
        assert DummyUniqueDocumentTarget.get_for_object(None) is None

    def test_get_for_object_returns_none_for_unsaved_object(self):
        unsaved = DummyPublicIdModel(name="unsaved")
        assert DummyUniqueDocumentTarget.get_for_object(unsaved) is None

    def test_row_is_cascade_deleted_with_its_document_id(self, dummy_instance):
        metadata = DummyUniqueDocumentTarget.get_or_create_for_object(dummy_instance)
        document_id_pk = metadata.target_id

        DocumentId.objects.filter(pk=document_id_pk).delete()

        assert not DummyUniqueDocumentTarget.objects.filter(pk=document_id_pk).exists()
