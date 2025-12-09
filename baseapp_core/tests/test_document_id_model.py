import uuid

import pytest
from django.contrib.contenttypes.models import ContentType

from baseapp_core.models import DocumentId
from testproject.testapp.models import DummyLegacyModel, DummyPublicIdModel
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


@pytest.mark.django_db
class TestDocumentIdModel:
    def test_str_representation(self):
        obj = DummyPublicIdModelFactory()
        content_type = ContentType.objects.get_for_model(obj.__class__)
        mapping = DocumentId.objects.get(
            content_type=content_type,
            object_id=obj.pk,
        )
        s = str(mapping)
        assert f"{content_type.model}:{obj.pk}" in s
        assert str(mapping.public_id) in s

    def test_get_public_id(self):
        obj = DummyPublicIdModelFactory()
        public_id = DocumentId.get_public_id_from_object(obj)
        assert public_id is not None

        public_id2 = DocumentId.get_public_id_from_object(obj)
        assert public_id2 == public_id

    def test_get_public_id_returns_none_for_unsaved(self):
        obj = DummyPublicIdModel(name="bar")
        result = DocumentId.get_public_id_from_object(obj)
        assert result is None

    def test_get_object_by_public_id_returns_object(self):
        obj = DummyPublicIdModelFactory()
        public_id = DocumentId.get_public_id_from_object(obj)
        found = DocumentId.get_object_by_public_id(public_id)
        assert found == obj

    def test_get_object_by_public_id_with_model_class(self):
        obj = DummyPublicIdModelFactory()
        public_id = DocumentId.get_public_id_from_object(obj)
        found = DocumentId.get_object_by_public_id(public_id, model_class=obj.__class__)
        assert found == obj

    def test_get_object_by_public_id_wrong_model_class_returns_none(self):
        obj = DummyPublicIdModelFactory()
        public_id = DocumentId.get_public_id_from_object(obj)

        found = DocumentId.get_object_by_public_id(public_id, model_class=DummyLegacyModel)
        assert found is None

    def test_get_object_by_public_id_invalid_id_returns_none(self):
        random_uuid = uuid.uuid4()
        found = DocumentId.get_object_by_public_id(random_uuid)
        assert found is None

    def test_unique_together_constraint(self):
        obj = DummyPublicIdModelFactory()
        content_type = ContentType.objects.get_for_model(obj.__class__)
        with pytest.raises(Exception):
            # Should raise IntegrityError or similar
            DocumentId.objects.create(
                content_type=content_type,
                object_id=obj.pk,
            )
