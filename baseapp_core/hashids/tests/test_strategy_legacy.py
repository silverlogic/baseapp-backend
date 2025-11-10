from unittest.mock import MagicMock

import pytest
from graphql_relay import to_global_id

from baseapp_core.graphql.relay import Node
from baseapp_core.hashids.strategies.legacy import (
    LegacyDRFResolverStrategy,
    LegacyGraphQLResolverStrategy,
    LegacyIdResolverStrategy,
    LegacyQuerysetAnnotatorStrategy,
)
from testproject.testapp.models import DummyLegacyModel
from testproject.testapp.tests.factories import DummyLegacyModelFactory


@pytest.mark.django_db
class TestLegacyIdResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return LegacyIdResolverStrategy()

    def test_get_id_from_instance_returns_legacy_id(self, resolver):
        instance = DummyLegacyModelFactory()
        assert resolver.get_id_from_instance(instance) == instance.pk

    def test_resolve_id_calls_mapping(self, resolver):
        dummy_obj = DummyLegacyModelFactory()
        result = resolver.resolve_id(dummy_obj.pk, model_cls=type(dummy_obj))
        assert result.pk == dummy_obj.pk

    def test_resolve_id_returns_none_for_nonexistent_id(self, resolver):
        random_id = 99999999  # unlikely to exist
        with pytest.raises(DummyLegacyModel.DoesNotExist):
            resolver.resolve_id(str(random_id), model_cls=DummyLegacyModel)

    def test_resolve_id_raises_for_invalid_id(self, resolver):
        invalid_id = "not-an-int"
        with pytest.raises(ValueError):
            resolver.resolve_id(invalid_id, model_cls=DummyLegacyModel)


@pytest.mark.django_db
class TestLegacyGraphQLResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return LegacyGraphQLResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_to_global_id_uses_id_resolver(self, resolver: LegacyGraphQLResolverStrategy):
        dummy_instance = DummyLegacyModelFactory()
        result = resolver.to_global_id(dummy_instance, "DummyLegacyModel", dummy_instance.pk)
        assert result == to_global_id("DummyLegacyModel", dummy_instance.pk)

    def test_get_node_from_global_id_using_pk_should_fail(
        self, resolver: LegacyGraphQLResolverStrategy
    ):
        info = MagicMock()
        dummy_instance = DummyLegacyModelFactory()
        only_type_mock = MagicMock()

        with pytest.raises(Exception) as e:
            resolver.get_node_from_global_id(info, dummy_instance.pk, only_type_mock)
            assert "Unable to parse global ID" in str(e.value)

    def test_get_node_from_global_id_using_global_id(
        self, resolver: LegacyGraphQLResolverStrategy, monkeypatch
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

    def test_get_node_from_global_id_using_global_id_without_only_type(
        self, resolver: LegacyGraphQLResolverStrategy
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

    def test_get_pk_from_global_id(self, resolver: LegacyGraphQLResolverStrategy):
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert resolver.get_pk_from_global_id(global_id) == str(dummy_instance.pk)

    def test_get_instance_from_global_id(self, resolver: LegacyGraphQLResolverStrategy):
        dummy_instance = DummyLegacyModelFactory()
        info = MagicMock()
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.model = DummyLegacyModel
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=graphene_type_mock))

        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert resolver.get_instance_from_global_id(info, global_id) == dummy_instance

    def test_get_instance_from_global_id_with_get_node(
        self, resolver: LegacyGraphQLResolverStrategy
    ):
        dummy_instance = DummyLegacyModelFactory()
        info = MagicMock()
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.model = DummyLegacyModel
        graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=graphene_type_mock))

        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        assert (
            resolver.get_instance_from_global_id(info, global_id, get_node=True) == dummy_instance
        )


@pytest.mark.django_db
class TestLegacyQuerysetAnnotatorStrategy:
    def test_annotate_do_nothing(self):
        DummyLegacyModelFactory()
        strategy = LegacyQuerysetAnnotatorStrategy()
        queryset = DummyLegacyModel.objects.all()
        annotated_queryset = strategy.annotate(DummyLegacyModel, queryset)
        assert annotated_queryset == queryset
        assert annotated_queryset.query.annotations == queryset.query.annotations


@pytest.mark.django_db
class TestLegacyDRFResolverStrategy:
    @pytest.fixture
    def resolver(self):
        return LegacyDRFResolverStrategy(id_resolver=LegacyIdResolverStrategy())

    def test_resolve_public_id_to_pk_returns_input(self, resolver):
        # legacy DRF resolver is a no-op and should return the input unchanged
        dummy = DummyLegacyModelFactory()
        assert resolver.resolve_public_id_to_pk(str(dummy.pk)) == str(dummy.pk)
