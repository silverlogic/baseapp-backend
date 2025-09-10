import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models

from baseapp_core.hashids.models import PublicIdMapping
from baseapp_core.tests.factories import UserFactory


@pytest.mark.django_db
class TestPublicIdMappingModel:
    def test_str_representation(self):
        obj = UserFactory()
        content_type = ContentType.objects.get_for_model(obj.__class__)
        mapping = PublicIdMapping.objects.create(
            content_type=content_type,
            object_id=obj.pk,
        )
        s = str(mapping)
        assert f"{content_type.model}:{obj.pk}" in s
        assert str(mapping.public_id) in s

    def test_get_or_create_public_id_creates_and_returns(self):
        obj = UserFactory()
        public_id, created = PublicIdMapping.get_or_create_public_id(obj)
        assert created is True
        assert public_id is not None

        # Calling again should not create a new mapping
        public_id2, created2 = PublicIdMapping.get_or_create_public_id(obj)
        assert created2 is False
        assert public_id2 == public_id

    def test_get_or_create_public_id_returns_none_for_unsaved(self):
        User = get_user_model()
        obj = User()
        result = PublicIdMapping.get_or_create_public_id(obj)
        assert result == (None, None)

    def test_get_object_by_public_id_returns_object(self):
        obj = UserFactory()
        public_id, _ = PublicIdMapping.get_or_create_public_id(obj)
        found = PublicIdMapping.get_object_by_public_id(public_id)
        assert found == obj

    def test_get_object_by_public_id_with_model_class(self):
        obj = UserFactory()
        public_id, _ = PublicIdMapping.get_or_create_public_id(obj)
        found = PublicIdMapping.get_object_by_public_id(public_id, model_class=obj.__class__)
        assert found == obj

    def test_get_object_by_public_id_wrong_model_class_returns_none(self):
        obj = UserFactory()
        public_id, _ = PublicIdMapping.get_or_create_public_id(obj)

        class OtherModel(models.Model):
            class Meta:
                app_label = "tests"

        found = PublicIdMapping.get_object_by_public_id(public_id, model_class=OtherModel)
        assert found is None

    def test_get_object_by_public_id_invalid_id_returns_none(self):
        random_uuid = uuid.uuid4()
        found = PublicIdMapping.get_object_by_public_id(random_uuid)
        assert found is None

    def test_unique_together_constraint(self):
        obj = UserFactory()
        content_type = ContentType.objects.get_for_model(obj.__class__)
        PublicIdMapping.objects.create(
            content_type=content_type,
            object_id=obj.pk,
        )
        with pytest.raises(Exception):
            # Should raise IntegrityError or similar
            PublicIdMapping.objects.create(
                content_type=content_type,
                object_id=obj.pk,
            )
