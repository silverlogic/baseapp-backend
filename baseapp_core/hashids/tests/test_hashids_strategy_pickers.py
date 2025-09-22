import uuid
from unittest.mock import MagicMock, patch

import pytest
from constance.test import override_config
from graphql_relay import to_global_id

from baseapp_core.graphql.relay import Node
from baseapp_core.hashids.strategies import (
    _is_public_id_logic_enabled,
    get_hashids_strategy_from_instance_or_cls,
    get_legacy_strategy,
    get_public_id_strategy,
    graphql_get_node_from_global_id_using_strategy,
    graphql_to_global_id_using_strategy,
)
from baseapp_core.hashids.strategies.bundle import HashidsStrategyBundle
from baseapp_core.hashids.strategies.legacy import (
    LegacyGraphQLResolverStrategy,
    LegacyIdResolverStrategy,
    LegacyQuerysetAnnotatorStrategy,
)
from baseapp_core.hashids.strategies.public_id import (
    PublicIdGraphQLResolverStrategy,
    PublicIdQuerysetAnnotatorStrategy,
    PublicIdResolverStrategy,
)
from testproject.testapp.models import DummyLegacyModel, DummyPublicIdModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyLegacyWithPkModelFactory,
    DummyPublicIdModelFactory,
)


@pytest.mark.django_db
class TestPublicIdLogicEnabled:
    def test_is_public_id_logic_enabled_returns_true_when_config_enabled(self):
        with override_config(ENABLE_PUBLIC_ID_LOGIC=True):
            assert _is_public_id_logic_enabled() is True

    def test_is_public_id_logic_enabled_returns_false_when_config_disabled(self):
        with override_config(ENABLE_PUBLIC_ID_LOGIC=False):
            assert _is_public_id_logic_enabled() is False


@pytest.mark.django_db
class TestStrategyGetters:
    def test_get_legacy_strategy_returns_correct_bundle(self):
        strategy = get_legacy_strategy()

        assert isinstance(strategy, HashidsStrategyBundle)
        assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
        assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
        assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_get_public_id_strategy_returns_correct_bundle(self):
        strategy = get_public_id_strategy()

        assert isinstance(strategy, HashidsStrategyBundle)
        assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
        assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
        assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_get_legacy_strategy_returns_different_instances(self):
        strategy1 = get_legacy_strategy()
        strategy2 = get_legacy_strategy()

        # Should return different instances
        assert strategy1 is not strategy2
        assert strategy1.id_resolver is not strategy2.id_resolver
        assert strategy1.graphql_resolver is not strategy2.graphql_resolver
        assert strategy1.queryset_annotator is not strategy2.queryset_annotator

    def test_get_public_id_strategy_returns_different_instances(self):
        strategy1 = get_public_id_strategy()
        strategy2 = get_public_id_strategy()

        # Should return different instances
        assert strategy1 is not strategy2
        assert strategy1.id_resolver is not strategy2.id_resolver
        assert strategy1.graphql_resolver is not strategy2.graphql_resolver
        assert strategy1.queryset_annotator is not strategy2.queryset_annotator


@pytest.mark.django_db
class TestGetHashidsStrategyFromInstanceOrCls:
    def test_returns_public_id_strategy_for_public_id_model_when_enabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_returns_public_id_strategy_for_public_id_model_class_when_enabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            strategy = get_hashids_strategy_from_instance_or_cls(DummyPublicIdModel)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_public_id_model_when_disabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=False
        ):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_when_enabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyLegacyModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_when_disabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=False
        ):
            dummy_instance = DummyLegacyModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_class(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            strategy = get_hashids_strategy_from_instance_or_cls(DummyLegacyModel)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)


@pytest.mark.django_db
class TestGraphQLToGlobalIdUsingStrategy:
    def test_uses_public_id_strategy_when_enabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyPublicIdModelFactory()

            result = graphql_to_global_id_using_strategy(
                dummy_instance, "DummyPublicIdModel", dummy_instance.pk
            )

            assert result == str(dummy_instance.public_id)

    def test_uses_legacy_strategy_when_disabled(self):
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=False
        ):
            dummy_instance = DummyLegacyModelFactory()

            result = graphql_to_global_id_using_strategy(
                dummy_instance, "DummyLegacyModel", dummy_instance.pk
            )

            expected_global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
            assert result == expected_global_id


@pytest.mark.django_db
class TestGraphQLGetNodeFromGlobalIdUsingStrategy:
    def test_uses_public_id_strategy_for_uuid4_global_id(self):
        dummy_instance = DummyPublicIdModelFactory()
        test_uuid = dummy_instance.public_id
        graphene_type_mock = MagicMock()
        graphene_type_mock._meta.name = "DummyPublicIdModel"
        graphene_type_mock._meta.interfaces = [Node]
        graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
        mock_info = MagicMock()
        mock_info.schema.get_type = MagicMock(
            return_value=MagicMock(graphene_type=graphene_type_mock)
        )

        result = graphql_get_node_from_global_id_using_strategy(mock_info, str(test_uuid))

        assert result.pk == dummy_instance.pk
        assert result.public_id == dummy_instance.public_id

    def test_uses_public_id_strategy_for_uuid4_with_only_type(self):
        dummy_instance = DummyPublicIdModelFactory()
        test_uuid = dummy_instance.public_id
        mock_info = MagicMock()
        mock_only_type = MagicMock()
        mock_only_type._meta.name = "DummyPublicIdModel"
        mock_only_type._meta.interfaces = [Node]
        mock_only_type.get_node = MagicMock(return_value=dummy_instance)
        mock_info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=mock_only_type))

        result = graphql_get_node_from_global_id_using_strategy(
            mock_info, str(test_uuid), mock_only_type
        )

        assert result.pk == dummy_instance.pk
        assert result.public_id == dummy_instance.public_id

    def test_returns_none_and_falls_back_to_legacy_for_nonexistent_uuid4(self):
        test_uuid = str(uuid.uuid4())  # Non-existent UUID4
        mock_info = MagicMock()

        # If it doesnt find by uuid, it will fallback to legacy strategy. In this case, it will raise a parse Exception.
        with pytest.raises(Exception) as e:
            graphql_get_node_from_global_id_using_strategy(mock_info, test_uuid)

        assert "Unable to parse global ID" in str(e.value)

    def test_uses_legacy_strategy_for_non_uuid4_global_id(self):
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        mock_info = MagicMock()

        only_type_mock = MagicMock()
        only_type_mock._meta.name = "DummyLegacyModel"
        only_type_mock._meta.interfaces = [Node]
        only_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info_schema_mock = MagicMock()
        info_schema_mock.get_type = MagicMock(return_value=MagicMock(graphene_type=only_type_mock))
        mock_info.schema = info_schema_mock

        result = graphql_get_node_from_global_id_using_strategy(mock_info, global_id)

        assert result.pk == dummy_instance.pk

    def test_uses_legacy_strategy_for_integer_id_should_fail(self):
        dummy_instance = DummyLegacyModelFactory()
        mock_info = MagicMock()
        mock_only_type = MagicMock()

        with pytest.raises(Exception) as e:
            graphql_get_node_from_global_id_using_strategy(
                mock_info, str(dummy_instance.pk), mock_only_type
            )
            assert (
                f"{dummy_instance.__class__.__name__} is not compatible with the PK strategy"
                in str(e.value)
            )

    def test_users_legacy_with_pk_model_with_pk_strategy(self):
        dummy_instance = DummyLegacyWithPkModelFactory()
        mock_info = MagicMock()
        mock_only_type = MagicMock()
        mock_only_type._meta.name = "DummyLegacyWithPkModel"
        mock_only_type._meta.interfaces = [Node]
        mock_only_type.get_node = MagicMock(return_value=dummy_instance)
        mock_info.schema.get_type = MagicMock(return_value=MagicMock(graphene_type=mock_only_type))

        result = graphql_get_node_from_global_id_using_strategy(
            mock_info, str(dummy_instance.pk), mock_only_type
        )
        assert result.pk == dummy_instance.pk


@pytest.mark.django_db
class TestHashidsStrategyIntegrationScenarios:
    def test_public_id_model_with_public_id_logic_enabled_uses_public_id_strategy(self):
        with override_config(ENABLE_PUBLIC_ID_LOGIC=True):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)

            resolved_id = strategy.id_resolver.get_id_from_instance(dummy_instance)
            assert resolved_id == dummy_instance.public_id

            resolved_instance = strategy.id_resolver.resolve_id(dummy_instance.public_id)
            assert resolved_instance.pk == dummy_instance.pk

    def test_public_id_model_with_public_id_logic_disabled_uses_legacy_strategy(self):
        with override_config(ENABLE_PUBLIC_ID_LOGIC=False):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)

            resolved_id = strategy.id_resolver.get_id_from_instance(dummy_instance)
            assert resolved_id == dummy_instance.pk

            resolved_instance = strategy.id_resolver.resolve_id(
                dummy_instance.pk, model_cls=DummyPublicIdModel
            )
            assert resolved_instance.pk == dummy_instance.pk

    def test_legacy_model_always_uses_legacy_strategy(self):
        for config_value in [True, False, None, ""]:
            with override_config(ENABLE_PUBLIC_ID_LOGIC=config_value):
                dummy_instance = DummyLegacyModelFactory()
                strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

                assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
                assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)

                resolved_id = strategy.id_resolver.get_id_from_instance(dummy_instance)
                assert resolved_id == dummy_instance.pk

    def test_uuid4_global_id_flow_with_public_id_logic_enabled(self):
        with override_config(ENABLE_PUBLIC_ID_LOGIC=True):
            dummy_instance = DummyPublicIdModelFactory()
            test_uuid = str(dummy_instance.public_id)
            graphene_type_mock = MagicMock()
            graphene_type_mock._meta.name = "DummyPublicIdModel"
            graphene_type_mock._meta.interfaces = [Node]
            graphene_type_mock.get_node = MagicMock(return_value=dummy_instance)
            mock_info = MagicMock()
            mock_info.schema.get_type = MagicMock(
                return_value=MagicMock(graphene_type=graphene_type_mock)
            )

            result = graphql_get_node_from_global_id_using_strategy(mock_info, test_uuid)

            assert result.pk == dummy_instance.pk
            assert result.public_id == dummy_instance.public_id

    def test_non_uuid4_global_id_uses_legacy_strategy_directly(self):
        dummy_instance = DummyLegacyModelFactory()
        global_id = to_global_id("DummyLegacyModel", dummy_instance.pk)
        mock_info = MagicMock()

        only_type_mock = MagicMock()
        only_type_mock._meta.name = "DummyLegacyModel"
        only_type_mock._meta.interfaces = [Node]
        only_type_mock.get_node = MagicMock(return_value=dummy_instance)
        info_schema_mock = MagicMock()
        info_schema_mock.get_type = MagicMock(return_value=MagicMock(graphene_type=only_type_mock))
        mock_info.schema = info_schema_mock

        result = graphql_get_node_from_global_id_using_strategy(mock_info, global_id)

        assert result.pk == dummy_instance.pk

    def test_mixed_strategy_usage_in_same_test(self):
        public_id_instance = DummyPublicIdModelFactory()
        legacy_instance = DummyLegacyModelFactory()

        with override_config(ENABLE_PUBLIC_ID_LOGIC=True):
            # Test public ID strategy
            public_id_strategy = get_hashids_strategy_from_instance_or_cls(public_id_instance)
            assert isinstance(public_id_strategy.id_resolver, PublicIdResolverStrategy)

            # Test legacy strategy
            legacy_strategy = get_hashids_strategy_from_instance_or_cls(legacy_instance)
            assert isinstance(legacy_strategy.id_resolver, LegacyIdResolverStrategy)

            public_id_resolved = public_id_strategy.id_resolver.resolve_id(
                public_id_instance.public_id
            )
            assert public_id_resolved.pk == public_id_instance.pk

            legacy_id_resolved = legacy_strategy.id_resolver.resolve_id(
                legacy_instance.pk, model_cls=DummyLegacyModel
            )
            assert legacy_id_resolved.pk == legacy_instance.pk
