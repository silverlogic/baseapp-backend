import uuid
from unittest.mock import MagicMock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from baseapp_core.graphql.relay import Node
from baseapp_core.hashids.strategies.public_id import (
    PublicIdDRFResolverStrategy,
    PublicIdGraphQLResolverStrategy,
    PublicIdQuerysetAnnotatorStrategy,
    PublicIdResolverStrategy,
)
from baseapp_core.models import DocumentId
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


@pytest.mark.django_db
class TestPublicIdResolverStrategy:
    @pytest.fixture
    def resolver(self) -> PublicIdResolverStrategy:
        return PublicIdResolverStrategy()

    def test_get_id_from_instance_returns_public_id(self, resolver) -> None:
        instance = DummyPublicIdModelFactory()
        assert resolver.get_id_from_instance(instance) == instance.public_id

    def test_resolve_id_calls_mapping(self, resolver) -> None:
        dummy_obj = DummyPublicIdModelFactory()
        result = resolver.resolve_id(dummy_obj.public_id, model_cls=type(dummy_obj))
        assert result.public_id == dummy_obj.public_id

    def test_resolve_id_returns_none_for_nonexistent_id(self, resolver) -> None:
        random_uuid = uuid.uuid4()
        result = resolver.resolve_id(str(random_uuid), model_cls=DummyPublicIdModel)
        assert result is None

    def test_resolve_id_returns_none_for_another_models_id(self, resolver) -> None:
        child = DummyPublicIdChildModelFactory()
        assert resolver.resolve_id(child.public_id, model_cls=DummyPublicIdModel) is None
        assert resolver.resolve_id(child.public_id, model_cls=DummyPublicIdChildModel) == child

    def test_resolve_id_without_model_cls_returns_any_model(self, resolver) -> None:
        child = DummyPublicIdChildModelFactory()
        assert resolver.resolve_id(child.public_id) == child

    def test_resolve_id_returns_none_for_a_dangling_mapping(self, resolver) -> None:
        dummy = DummyPublicIdModelFactory()
        public_id = dummy.public_id
        DummyPublicIdModel.objects.filter(pk=dummy.pk)._raw_delete(DummyPublicIdModel.objects.db)
        DocumentId.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(DummyPublicIdModel),
            object_id=dummy.pk,
            defaults={"public_id": public_id},
        )
        assert resolver.resolve_id(public_id, model_cls=DummyPublicIdModel) is None

    def test_get_id_from_instance_reads_prefetched_document(
        self, resolver, django_assert_num_queries
    ) -> None:
        dummy = DummyPublicIdModelFactory()
        expected = dummy.public_id
        instance = DummyPublicIdModel.objects.prefetch_related("document").get(pk=dummy.pk)
        with django_assert_num_queries(0):
            assert resolver.get_id_from_instance(instance) == expected

    def test_get_id_from_instance_reads_empty_prefetched_document(
        self, resolver, django_assert_num_queries
    ) -> None:
        dummy = DummyPublicIdModelFactory()
        DocumentId.objects.filter(object_id=dummy.pk).delete()
        instance = DummyPublicIdModel.objects.prefetch_related("document").get(pk=dummy.pk)
        with django_assert_num_queries(0):
            assert resolver.get_id_from_instance(instance) is None

    def test_get_id_from_instance_reads_prefetched_related_document(
        self, resolver, django_assert_num_queries
    ) -> None:
        DummyPublicIdChildModelFactory.create_batch(3)
        children = list(DummyPublicIdChildModel.objects.prefetch_related("parent__document"))
        with django_assert_num_queries(0):
            for child in children:
                assert resolver.get_id_from_instance(child.parent) is not None

    def test_resolve_id_returns_none_for_invalid_uuid(self, resolver) -> None:
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.resolve_id(invalid_id, model_cls=DummyPublicIdModel)


@pytest.mark.django_db
class TestPublicIdGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self) -> PublicIdGraphQLResolverStrategy:
        return PublicIdGraphQLResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: PublicIdGraphQLResolverStrategy) -> None:
        dummy_instance = DummyPublicIdModelFactory()
        result = resolver.to_global_id(dummy_instance, DummyPublicIdModel, dummy_instance.pk)
        assert result == str(dummy_instance.public_id)

    def test_to_global_id_when_public_id_is_empty(
        self, resolver: PublicIdGraphQLResolverStrategy
    ) -> None:
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, DummyLegacyModel, dummy_instance.pk)
        assert result is None

    def test_get_node_from_global_id_uses_resolve_id(
        self, resolver: PublicIdGraphQLResolverStrategy
    ) -> None:
        dummy_instance = DummyPublicIdModelFactory()
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.name = "DummyPublicIdModel"
        graphene_type_mock._meta.interfaces = [Node]
        graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
        mock_info = MagicMock()
        mock_info.schema.get_type = MagicMock(
            return_value=MagicMock(graphene_type=graphene_type_mock)
        )

        result = resolver.get_node_from_global_id(mock_info, dummy_instance.public_id)

        assert result.pk == dummy_instance.pk

    def test_get_node_from_global_id_returns_none_for_nonexistent_id(
        self, resolver: PublicIdGraphQLResolverStrategy
    ) -> None:
        info = MagicMock()
        random_uuid = uuid.uuid4()
        with pytest.raises(resolver.NoInstanceFound):
            resolver.get_node_from_global_id(info, str(random_uuid))

    def test_get_node_from_global_id_returns_none_for_invalid_uuid(
        self, resolver: PublicIdGraphQLResolverStrategy
    ) -> None:
        info = MagicMock()
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.get_node_from_global_id(info, invalid_id)

    def test_get_pk_from_global_id(self, resolver: PublicIdGraphQLResolverStrategy) -> None:
        dummy_instance = DummyPublicIdModelFactory()
        assert resolver.get_pk_from_global_id(dummy_instance.public_id) == dummy_instance.pk

    def test_get_instance_from_global_id(self, resolver: PublicIdGraphQLResolverStrategy) -> None:
        dummy_instance = DummyPublicIdModelFactory()
        assert (
            resolver.get_instance_from_global_id(None, dummy_instance.public_id) == dummy_instance
        )

    def test_get_instance_from_global_id_with_get_node(
        self, resolver: PublicIdGraphQLResolverStrategy
    ) -> None:
        dummy_instance = DummyPublicIdModelFactory()
        info = MagicMock()
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.name = "DummyPublicIdModel"
        graphene_type_mock._meta.interfaces = [Node]
        graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=graphene_type_mock))
        assert (
            resolver.get_instance_from_global_id(info, dummy_instance.public_id, get_node=True)
            == dummy_instance
        )


@pytest.mark.django_db
class TestPublicIdQuerysetAnnotatorStrategy:
    def test_get_annotations_for_a_foreign_key(self) -> None:
        child = DummyPublicIdChildModelFactory()
        strategy = PublicIdQuerysetAnnotatorStrategy()
        annotations = strategy.get_annotations(
            DummyPublicIdModel, field="parent", alias="parent_public_id"
        )
        row = DummyPublicIdChildModel.objects.annotate(**annotations).get(pk=child.pk)
        assert row.parent_public_id == child.parent.public_id

    def test_annotate_adds_mapped_public_id(self) -> None:
        DummyPublicIdModelFactory()
        strategy = PublicIdQuerysetAnnotatorStrategy()
        queryset = DummyPublicIdModel.objects.all()
        annotated_queryset = strategy.annotate(DummyPublicIdModel, queryset)

        assert "mapped_public_id" in annotated_queryset.query.annotations
        assert hasattr(annotated_queryset.first(), "mapped_public_id") is True


@pytest.mark.django_db
class TestPublicIdDRFResolverStrategy:
    @pytest.fixture
    def resolver(self) -> PublicIdDRFResolverStrategy:
        return PublicIdDRFResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_resolve_public_id_to_pk_returns_object_id(self, resolver) -> None:
        dummy = DummyPublicIdModelFactory()
        result = resolver.resolve_public_id_to_pk(str(dummy.public_id))
        assert result == dummy.pk

    def test_resolve_public_id_to_pk_checks_the_expected_model(self, resolver) -> None:
        dummy = DummyPublicIdModelFactory()
        result = resolver.resolve_public_id_to_pk(
            str(dummy.public_id), expected_model=DummyPublicIdModel
        )
        assert result == dummy.pk

    def test_resolve_public_id_to_pk_rejects_another_models_public_id(self, resolver) -> None:
        child = DummyPublicIdChildModelFactory()
        with pytest.raises(resolver.NoInstanceFound):
            resolver.resolve_public_id_to_pk(
                str(child.public_id), expected_model=DummyPublicIdModel
            )

    def test_resolve_public_id_to_pk_returns_none_for_unknown_public_id(self, resolver) -> None:
        assert (
            resolver.resolve_public_id_to_pk(str(uuid.uuid4()), expected_model=DummyPublicIdModel)
            is None
        )
