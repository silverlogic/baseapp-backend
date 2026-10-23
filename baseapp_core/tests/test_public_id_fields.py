import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from rest_framework import serializers

from baseapp_core.hashids.strategies import annotate_public_ids
from baseapp_core.rest_framework.fields import PublicIdField, PublicIdRelatedField
from testproject.testapp.models import (
    DummyLegacyModel,
    DummyPublicIdChildModel,
    DummyPublicIdModel,
)
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdChildModelFactory,
    DummyPublicIdModelFactory,
)

pytestmark = pytest.mark.django_db


class DummySerializer(serializers.ModelSerializer):
    id = PublicIdField()

    class Meta:
        model = DummyPublicIdModel
        fields = ("id", "name")


class ChildSerializer(serializers.ModelSerializer):
    id = PublicIdField()
    parent = PublicIdRelatedField(queryset=DummyPublicIdModel.objects.all())
    previous_parent = PublicIdRelatedField(
        source="previous.parent", read_only=True, allow_null=True
    )
    legacy = PublicIdRelatedField(
        queryset=DummyLegacyModel.objects.all(), required=False, allow_null=True
    )
    tags = PublicIdRelatedField(
        queryset=DummyPublicIdModel.objects.all(), many=True, required=False
    )

    class Meta:
        model = DummyPublicIdChildModel
        fields = ("id", "name", "parent", "previous_parent", "legacy", "tags")


class TestPublicIdField:
    def test_renders_public_id(self) -> None:
        dummy = DummyPublicIdModelFactory()
        assert DummySerializer(dummy).data["id"] == str(dummy.public_id)

    def test_renders_a_related_object(self) -> None:
        child = DummyPublicIdChildModelFactory()
        field = PublicIdField(source="parent")
        field.bind("parent_id", serializers.Serializer())
        assert field.to_representation(field.get_attribute(child)) == str(child.parent.public_id)

    def test_renders_pk_for_models_without_public_ids(self) -> None:
        legacy = DummyLegacyModelFactory()
        assert PublicIdField().to_representation(legacy) == legacy.pk

    def test_is_read_only(self) -> None:
        serializer = DummySerializer(data={"id": str(uuid.uuid4()), "name": "x"})
        assert serializer.is_valid(), serializer.errors
        assert "id" not in serializer.validated_data


class TestPublicIdRelatedField:
    def test_renders_public_ids(self) -> None:
        legacy = DummyLegacyModelFactory()
        previous = DummyPublicIdChildModelFactory()
        child = DummyPublicIdChildModelFactory(previous=previous, legacy=legacy)
        tag = DummyPublicIdModelFactory()
        child.tags.add(tag)

        data = ChildSerializer(child).data

        assert data["id"] == str(child.public_id)
        assert data["parent"] == str(child.parent.public_id)
        assert data["previous_parent"] == str(previous.parent.public_id)
        assert data["legacy"] == legacy.pk
        assert data["tags"] == [str(tag.public_id)]

    def test_renders_null(self) -> None:
        child = DummyPublicIdChildModelFactory()
        data = ChildSerializer(child).data
        assert data["previous_parent"] is None
        assert data["legacy"] is None
        assert data["tags"] == []

    def test_annotated_list_costs_no_query_per_row(self, django_assert_num_queries) -> None:
        for _ in range(3):
            child = DummyPublicIdChildModelFactory(previous=DummyPublicIdChildModelFactory())
            child.tags.add(DummyPublicIdModelFactory())

        queryset = annotate_public_ids(
            DummyPublicIdChildModel.objects.prefetch_related("tags__document"),
            "parent",
            "previous__parent",
        )
        # 1 for the rows, 1 for tags and 1 for the tags' documents.
        with django_assert_num_queries(3):
            data = ChildSerializer(queryset, many=True).data
        assert len(data) == 6
        assert all(row["parent"] for row in data)

    def test_prefetched_document_costs_no_query_per_row(self, django_assert_num_queries) -> None:
        DummyPublicIdChildModelFactory.create_batch(3)

        class ParentOnlySerializer(serializers.ModelSerializer):
            parent = PublicIdRelatedField(read_only=True)

            class Meta:
                model = DummyPublicIdChildModel
                fields = ("parent",)

        queryset = DummyPublicIdChildModel.objects.prefetch_related("parent__document")
        # Warm the content type cache, so the count does not depend on test order.
        ContentType.objects.get_for_model(DummyPublicIdModel)
        # 1 for the rows, 1 for the parents and 1 for their documents.
        with django_assert_num_queries(3):
            data = ParentOnlySerializer(queryset, many=True).data
        assert all(row["parent"] for row in data)

    def test_accepts_public_ids(self) -> None:
        parent = DummyPublicIdModelFactory()
        tag = DummyPublicIdModelFactory()
        legacy = DummyLegacyModelFactory()
        serializer = ChildSerializer(
            data={
                "name": "child",
                "parent": str(parent.public_id),
                "legacy": legacy.pk,
                "tags": [str(tag.public_id)],
            }
        )
        assert serializer.is_valid(), serializer.errors
        child = serializer.save()
        assert child.parent == parent
        assert child.legacy == legacy
        assert list(child.tags.all()) == [tag]

    def test_accepts_pks_by_default(self) -> None:
        parent = DummyPublicIdModelFactory()
        serializer = ChildSerializer(data={"name": "child", "parent": parent.pk})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["parent"] == parent

    @override_settings(BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP=False)
    def test_rejects_pks_when_disabled(self) -> None:
        parent = DummyPublicIdModelFactory()
        legacy = DummyLegacyModelFactory()
        serializer = ChildSerializer(
            data={"name": "child", "parent": parent.pk, "legacy": legacy.pk}
        )
        assert not serializer.is_valid()
        assert set(serializer.errors) == {"parent"}

    def test_rejects_pks_when_disabled_on_the_field(self) -> None:
        parent = DummyPublicIdModelFactory()
        field = PublicIdRelatedField(
            queryset=DummyPublicIdModel.objects.all(), allow_pk_lookup=False
        )
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value(parent.pk)
        assert field.to_internal_value(str(parent.public_id)) == parent

    def test_rejects_another_models_public_id(self) -> None:
        DummyPublicIdModelFactory.create_batch(2)
        child = DummyPublicIdChildModelFactory()
        serializer = ChildSerializer(
            data={"name": "x", "parent": str(child.public_id), "tags": [str(child.public_id)]}
        )
        assert not serializer.is_valid()
        assert set(serializer.errors) == {"parent", "tags"}

    @pytest.mark.parametrize("value", [str(uuid.uuid4()), "abc", "999999", True, 1.5, {}])
    def test_rejects_invalid_values(self, value) -> None:
        DummyPublicIdModelFactory()
        serializer = ChildSerializer(data={"name": "x", "parent": value})
        assert not serializer.is_valid()
        assert "parent" in serializer.errors

    def test_respects_the_queryset(self) -> None:
        parent = DummyPublicIdModelFactory()
        field = PublicIdRelatedField(queryset=DummyPublicIdModel.objects.exclude(pk=parent.pk))
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value(str(parent.public_id))

    def test_legacy_model_rejects_garbage(self) -> None:
        field = PublicIdRelatedField(queryset=DummyLegacyModel.objects.all())
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("abc")

    @override_settings(ENABLE_PUBLIC_ID_LOGIC=False)
    def test_behaves_like_a_pk_field_without_public_id_logic(self) -> None:
        child = DummyPublicIdChildModelFactory()
        assert ChildSerializer(child).data["parent"] == child.parent.pk
        field = PublicIdRelatedField(queryset=DummyPublicIdModel.objects.all())
        assert field.to_internal_value(child.parent.pk) == child.parent
