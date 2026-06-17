import pytest
from django.contrib.contenttypes.models import ContentType

from baseapp_core.models import DocumentId
from testproject.testapp.models import DummyDocumentTarget, DummyPublicIdModel
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


@pytest.mark.django_db
class TestDocumentIdTargetMixin:
    @pytest.fixture
    def dummy_instance(self, db):
        return DummyPublicIdModelFactory()

    def test_target_document_is_non_unique_foreign_key_to_document_id(self):
        field = DummyDocumentTarget._meta.get_field("target_document")
        assert field.many_to_one is True
        assert field.one_to_one is False
        assert field.null is False
        assert field.related_model is DocumentId

    def test_related_name_is_app_label_and_class_scoped(self, dummy_instance):
        row = DummyDocumentTarget(target=dummy_instance)
        row.save()
        assert list(row.target_document.testapp_dummydocumenttarget.all()) == [row]

    def test_setting_target_creates_document_and_resolves_back(self, dummy_instance):
        row = DummyDocumentTarget(target=dummy_instance)
        row.save()

        assert row.target_document is not None
        assert DocumentId.objects.filter(pk=row.target_document_id).exists()
        assert row.target == dummy_instance

    def test_target_resolves_from_persisted_document(self, dummy_instance):
        row = DummyDocumentTarget.objects.create(target=dummy_instance)

        reloaded = DummyDocumentTarget.objects.get(pk=row.pk)
        assert reloaded.target == dummy_instance

    def test_target_getter_is_cached(self, dummy_instance):
        row = DummyDocumentTarget.objects.create(target=dummy_instance)
        reloaded = DummyDocumentTarget.objects.get(pk=row.pk)

        first = reloaded.target
        assert reloaded._target_object_cache is first
        assert reloaded.target is first

    def test_target_getter_returns_none_when_unset(self):
        assert DummyDocumentTarget().target is None

    def test_setting_target_to_none_clears_document(self, dummy_instance):
        row = DummyDocumentTarget(target=dummy_instance)
        row.target = None
        assert row.target_document_id is None
        assert row.target is None

    def test_target_metadata_shortcuts(self, dummy_instance):
        row = DummyDocumentTarget.objects.create(target=dummy_instance)
        ct = ContentType.objects.get_for_model(DummyPublicIdModel)

        assert row.target_content_type == ct
        assert row.target_content_type_id == ct.pk
        assert row.target_object_id == dummy_instance.pk

    def test_target_metadata_shortcuts_none_when_unset(self):
        row = DummyDocumentTarget()
        assert row.target_content_type is None
        assert row.target_content_type_id is None
        assert row.target_object_id is None

    def test_multiple_rows_can_share_the_same_target(self, dummy_instance):
        first = DummyDocumentTarget.objects.create(target=dummy_instance)
        second = DummyDocumentTarget.objects.create(target=dummy_instance)

        assert first.target_document_id == second.target_document_id
        assert (
            DummyDocumentTarget.objects.filter(target_document_id=first.target_document_id).count()
            == 2
        )

    def test_rows_are_cascade_deleted_with_their_document(self, dummy_instance):
        row = DummyDocumentTarget.objects.create(target=dummy_instance)
        document_id = row.target_document_id

        DocumentId.objects.filter(pk=document_id).delete()

        assert not DummyDocumentTarget.objects.filter(pk=row.pk).exists()
