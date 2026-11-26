import pytest
from django.test import override_settings
from rest_framework import serializers

from baseapp_core.rest_framework.fields import PublicIdRelatedField
from baseapp_core.rest_framework.serializers import ModelSerializer
from testproject.testapp.models import DummyPublicIdChildModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
    DummyPublicIdModelFactory,
)

pytestmark = pytest.mark.django_db


class AutoChildSerializer(ModelSerializer):
    class Meta:
        model = DummyPublicIdChildModel
        fields = ("id", "name", "parent", "legacy", "tags")


class TestModelSerializerRelatedFields:
    def test_foreign_keys_stay_pks_by_default(self) -> None:
        child = DummyPublicIdChildModelFactory()
        fields = AutoChildSerializer().fields
        assert type(fields["parent"]) is serializers.PrimaryKeyRelatedField
        data = AutoChildSerializer(child).data
        assert data["id"] == str(child.public_id)
        assert data["parent"] == child.parent.pk

    @override_settings(BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS=True)
    def test_foreign_keys_use_public_ids_when_enabled(self) -> None:
        legacy = DummyLegacyModelFactory()
        child = DummyPublicIdChildModelFactory(legacy=legacy)
        tag = DummyPublicIdModelFactory()
        child.tags.add(tag)

        fields = AutoChildSerializer().fields
        assert isinstance(fields["parent"], PublicIdRelatedField)
        assert isinstance(fields["tags"].child_relation, PublicIdRelatedField)
        assert type(fields["legacy"]) is serializers.PrimaryKeyRelatedField

        data = AutoChildSerializer(child).data
        assert data["parent"] == str(child.parent.public_id)
        assert data["tags"] == [str(tag.public_id)]
        assert data["legacy"] == legacy.pk

        new_parent = DummyPublicIdModelFactory()
        serializer = AutoChildSerializer(
            child, data={"parent": str(new_parent.public_id)}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().parent == new_parent
