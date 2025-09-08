import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import models

from baseapp_core.hashids.models import PublicIdMapping
from testproject.testapp.models import DummyPublicIdModel
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


@pytest.mark.django_db
class TestPublicIdMixin:
    @pytest.fixture
    def dummy_instance(self, db):
        obj = DummyPublicIdModelFactory()
        return obj

    @pytest.fixture
    def dummy_content_type(self):
        return ContentType.objects.get_for_model(DummyPublicIdModel)

    def test_public_id_property_creates_mapping(self, dummy_instance, dummy_content_type):
        # Assert that only after accessing the public_id property, the mapping is created
        assert (
            PublicIdMapping.objects.filter(
                object_id=dummy_instance.pk, content_type=dummy_content_type
            ).exists()
            is False
        )
        public_id = dummy_instance.public_id
        assert public_id is not None
        mapping = PublicIdMapping.objects.get(
            object_id=dummy_instance.pk, content_type=dummy_content_type
        )
        assert mapping.public_id == public_id

    def test_public_id_property_returns_same_id(self, dummy_instance):
        public_id1 = dummy_instance.public_id
        public_id2 = dummy_instance.public_id
        assert public_id1 == public_id2

    def test_public_id_property_returns_none_for_unsaved(self):
        obj = DummyPublicIdModel(name="bar")
        assert obj.pk is None
        assert obj.public_id is None

    def test_get_by_public_id_returns_instance(self, dummy_instance):
        public_id = dummy_instance.public_id
        found = DummyPublicIdModel.get_by_public_id(public_id)
        assert found == dummy_instance

    def test_get_by_public_id_returns_none_for_invalid_id(self):
        random_uuid = uuid.uuid4()
        found = DummyPublicIdModel.get_by_public_id(random_uuid)
        assert found is None

    def test_get_by_public_id_wrong_model_returns_none(self, dummy_instance):
        public_id = dummy_instance.public_id

        class OtherModel(models.Model):
            class Meta:
                app_label = "tests"

        found = OtherModel.objects.filter(pk=public_id).first()
        assert found is None
        # Also, using the mixin's get_by_public_id should not return an instance of OtherModel
        assert DummyPublicIdModel.get_by_public_id(public_id) == dummy_instance

    def test_unique_public_id_per_instance(self, dummy_instance):
        # Create another instance and ensure it gets a different public_id
        obj2 = DummyPublicIdModelFactory()
        assert obj2.public_id != dummy_instance.public_id

    def test_public_id_mapping_deleted_on_model_delete(self, dummy_instance, dummy_content_type):
        public_id = dummy_instance.public_id
        mapping = PublicIdMapping.objects.get(
            object_id=dummy_instance.pk, content_type=dummy_content_type
        )
        assert mapping.public_id == public_id

        dummy_instance.delete()

        with pytest.raises(PublicIdMapping.DoesNotExist):
            PublicIdMapping.objects.get(
                object_id=dummy_instance.pk, content_type=dummy_content_type
            )

    def test_public_id_mapping_deleted_only_for_that_instance(
        self, dummy_instance, dummy_content_type
    ):
        dummy_instance.public_id
        obj2 = DummyPublicIdModelFactory()
        obj2.public_id

        assert PublicIdMapping.objects.filter(
            object_id=dummy_instance.pk, content_type=dummy_content_type
        ).exists()
        assert PublicIdMapping.objects.filter(
            object_id=obj2.pk, content_type=dummy_content_type
        ).exists()

        dummy_instance.delete()

        assert not PublicIdMapping.objects.filter(
            object_id=dummy_instance.pk, content_type=dummy_content_type
        ).exists()
        assert PublicIdMapping.objects.filter(
            object_id=obj2.pk, content_type=dummy_content_type
        ).exists()

    def test_public_id_mapping_trigger_attached(self):
        triggers = getattr(DummyPublicIdModel._meta, "triggers", [])
        trigger_names = [t.name for t in triggers]
        assert "delete_public_id_mapping" in trigger_names
