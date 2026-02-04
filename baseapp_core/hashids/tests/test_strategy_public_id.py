import uuid
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ValidationError

from baseapp_core.graphql.relay import Node
from baseapp_core.hashids.strategies.public_id import (
    PublicIdDRFResolverStrategy,
    PublicIdGraphQLResolverStrategy,
    PublicIdQuerysetAnnotatorStrategy,
    PublicIdResolverStrategy,
)
from testproject.testapp.models import DummyLegacyModel, DummyPublicIdModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdModelFactory,
)


@pytest.mark.django_db
class TestPublicIdResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return PublicIdResolverStrategy()

    def test_get_id_from_instance_returns_public_id(self, resolver):
        instance = DummyPublicIdModelFactory()
        assert resolver.get_id_from_instance(instance) == instance.public_id

    def test_resolve_id_calls_mapping(self, resolver):
        dummy_obj = DummyPublicIdModelFactory()
        result = resolver.resolve_id(dummy_obj.public_id, model_cls=type(dummy_obj))
        assert result.public_id == dummy_obj.public_id

    def test_resolve_id_returns_none_for_nonexistent_id(self, resolver):
        random_uuid = uuid.uuid4()
        result = resolver.resolve_id(str(random_uuid), model_cls=DummyPublicIdModel)
        assert result is None

    def test_resolve_id_returns_none_for_invalid_uuid(self, resolver):
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.resolve_id(invalid_id, model_cls=DummyPublicIdModel)


@pytest.mark.django_db
class TestPublicIdGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return PublicIdGraphQLResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: PublicIdGraphQLResolverStrategy):
        dummy_instance = DummyPublicIdModelFactory()
        result = resolver.to_global_id(dummy_instance, DummyPublicIdModel, dummy_instance.pk)
        assert result == str(dummy_instance.public_id)

    def test_to_global_id_when_public_id_is_empty(self, resolver: PublicIdGraphQLResolverStrategy):
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, DummyLegacyModel, dummy_instance.pk)
        assert result is None

    def test_get_node_from_global_id_uses_resolve_id(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
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
    ):
        info = MagicMock()
        random_uuid = uuid.uuid4()
        with pytest.raises(resolver.NoInstanceFound):
            resolver.get_node_from_global_id(info, str(random_uuid))

    def test_get_node_from_global_id_returns_none_for_invalid_uuid(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
        info = MagicMock()
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.get_node_from_global_id(info, invalid_id)

    def test_get_pk_from_global_id(self, resolver: PublicIdGraphQLResolverStrategy):
        dummy_instance = DummyPublicIdModelFactory()
        assert resolver.get_pk_from_global_id(dummy_instance.public_id) == dummy_instance.pk

    def test_get_instance_from_global_id(self, resolver: PublicIdGraphQLResolverStrategy):
        dummy_instance = DummyPublicIdModelFactory()
        assert (
            resolver.get_instance_from_global_id(None, dummy_instance.public_id) == dummy_instance
        )

    def test_get_instance_from_global_id_with_get_node(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
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
    def test_annotate_adds_mapped_public_id(self):
        DummyPublicIdModelFactory()
        strategy = PublicIdQuerysetAnnotatorStrategy()
        queryset = DummyPublicIdModel.objects.all()
        annotated_queryset = strategy.annotate(DummyPublicIdModel, queryset)

        assert "mapped_public_id" in annotated_queryset.query.annotations
        assert hasattr(annotated_queryset.first(), "mapped_public_id") is True


@pytest.mark.django_db
class TestPublicIdDRFResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return PublicIdDRFResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_resolve_public_id_to_pk_returns_object_id(self, resolver):
        dummy = DummyPublicIdModelFactory()
        result = resolver.resolve_public_id_to_pk(str(dummy.public_id))
        assert result == dummy.pk
