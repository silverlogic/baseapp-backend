from unittest.mock import MagicMock

import pytest
from graphql_relay import to_global_id

from baseapp_core.graphql.relay import Node
from baseapp_core.hashids.strategies.legacy import LegacyIdResolverStrategy
from baseapp_core.hashids.strategies.pk import PkGraphQLResolverStrategy
from testproject.testapp.tests.factories import DummyLegacyModelFactory


@pytest.mark.django_db
class TestPkGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return PkGraphQLResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: PkGraphQLResolverStrategy):
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, "DummyLegacyModel", dummy_instance.pk)
        assert result == to_global_id("DummyLegacyModel", dummy_instance.pk)

    def test_get_node_from_global_id_using_pk(self, resolver: PkGraphQLResolverStrategy):
        info = MagicMock()
        dummy_instance = DummyLegacyModelFactory()
        only_type_mock = MagicMock()
        only_type_mock._meta.name = "DummyLegacyModel"
        only_type_mock._meta.interfaces = [Node]
        only_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=only_type_mock))

        result = resolver.get_node_from_global_id(info, dummy_instance.pk, only_type_mock)
        assert result.pk == dummy_instance.pk

    def test_get_node_from_global_id_using_global_id(
        self, resolver: PkGraphQLResolverStrategy, monkeypatch
    ):
        info = MagicMock()
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        only_type_mock = MagicMock()
        only_type_mock._meta.name = "DummyLegacyModel"
        only_type_mock._meta.interfaces = [Node]
        only_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=only_type_mock))

        result = resolver.get_node_from_global_id(info, global_id, only_type_mock)
        assert result.pk == dummy_instance.pk

    def test_get_from_global_id_using_pk_without_only_type(
        self, resolver: PkGraphQLResolverStrategy
    ):
        info = MagicMock()
        dummy_instance = DummyLegacyModelFactory()
        with pytest.raises(Exception) as e:
            resolver.get_node_from_global_id(info, dummy_instance.pk)
            assert "Can't resolve PK query without a specific type provided" in str(e.value)

    def test_get_from_global_id_using_global_id_without_only_type(
        self, resolver: PkGraphQLResolverStrategy
    ):
        info = MagicMock()
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.name = "DummyLegacyModel"
        graphene_type_mock._meta.interfaces = [Node]
        graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=graphene_type_mock))

        result = resolver.get_node_from_global_id(info, global_id)
        assert result.pk == dummy_instance.pk
