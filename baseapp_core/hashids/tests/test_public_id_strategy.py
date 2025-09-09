import uuid
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ValidationError

from baseapp_core.hashids.strategies.public_id import graphql_resolver
from baseapp_core.hashids.strategies.public_id.graphql_resolver import (
    PublicIdGraphQLResolverStrategy,
)
from baseapp_core.hashids.strategies.public_id.id_resolver import (
    PublicIdResolverStrategy,
)
from testproject.testapp.models import DummyPublicIdModel
from testproject.testapp.tests.factories import DummyPublicIdModelFactory


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
        result = resolver.resolve_id(dummy_obj.public_id, type(dummy_obj))
        assert result.public_id == dummy_obj.public_id

    def test_resolve_id_returns_none_for_nonexistent_id(self, resolver):
        random_uuid = uuid.uuid4()
        result = resolver.resolve_id(str(random_uuid), DummyPublicIdModel)
        assert result is None

    def test_resolve_id_returns_none_for_invalid_uuid(self, resolver):
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.resolve_id(invalid_id, DummyPublicIdModel)


@pytest.mark.django_db
class TestPublicIdGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return PublicIdGraphQLResolverStrategy(id_resolver=PublicIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(
        self, resolver: PublicIdGraphQLResolverStrategy, monkeypatch
    ):
        dummy_instance = DummyPublicIdModelFactory()

        monkeypatch.setattr(
            graphql_resolver,
            "get_model_from_graphql_object_type",
            lambda type_: DummyPublicIdModel,
        )

        result = resolver.to_global_id(DummyPublicIdModel, dummy_instance.pk)
        assert result == dummy_instance.public_id

    def test_get_node_from_global_id_uses_resolve_id(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
        info = MagicMock()
        dummy_instance = DummyPublicIdModelFactory()
        result = resolver.get_node_from_global_id(info, dummy_instance.public_id)
        assert result.pk == dummy_instance.pk

    def test_get_node_from_global_id_returns_none_for_nonexistent_id(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
        info = MagicMock()
        random_uuid = uuid.uuid4()
        result = resolver.get_node_from_global_id(info, str(random_uuid))
        assert result is None

    def test_get_node_from_global_id_returns_none_for_invalid_uuid(
        self, resolver: PublicIdGraphQLResolverStrategy
    ):
        info = MagicMock()
        invalid_id = "not-a-uuid"
        with pytest.raises(ValidationError):
            resolver.get_node_from_global_id(info, invalid_id)
