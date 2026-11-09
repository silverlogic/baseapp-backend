from unittest.mock import patch

import pytest
from django.test import override_settings

from baseapp_core.hashids.strategies import (
    _is_public_id_logic_enabled,
    get_hashids_strategy_from_instance_or_cls,
    get_legacy_strategy,
    get_public_id_strategy,
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
from baseapp_core.hashids.utils import to_global_id
from testproject.testapp.models import DummyLegacyModel, DummyPublicIdModel
from testproject.testapp.tests.factories import (
    DummyLegacyModelFactory,
    DummyPublicIdModelFactory,
)


@pytest.mark.django_db
class TestPublicIdLogicEnabled:
    def test_enabled_by_the_setting(self, settings) -> None:
        settings.ENABLE_PUBLIC_ID_LOGIC = True
        assert _is_public_id_logic_enabled() is True

    def test_disabled_by_the_setting(self, settings) -> None:
        settings.ENABLE_PUBLIC_ID_LOGIC = False
        assert _is_public_id_logic_enabled() is False

    def test_enabled_by_default(self, settings) -> None:
        del settings.ENABLE_PUBLIC_ID_LOGIC
        assert _is_public_id_logic_enabled() is True


@pytest.mark.django_db
class TestStrategyGetters:
    def test_get_legacy_strategy_returns_correct_bundle(self) -> None:
        strategy = get_legacy_strategy()

        assert isinstance(strategy, HashidsStrategyBundle)
        assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
        assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
        assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_get_public_id_strategy_returns_correct_bundle(self) -> None:
        strategy = get_public_id_strategy()

        assert isinstance(strategy, HashidsStrategyBundle)
        assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
        assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
        assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_get_legacy_strategy_returns_different_instances(self) -> None:
        strategy1 = get_legacy_strategy()
        strategy2 = get_legacy_strategy()

        # Should return different instances
        assert strategy1 is not strategy2
        assert strategy1.id_resolver is not strategy2.id_resolver
        assert strategy1.graphql_resolver is not strategy2.graphql_resolver
        assert strategy1.queryset_annotator is not strategy2.queryset_annotator

    def test_get_public_id_strategy_returns_different_instances(self) -> None:
        strategy1 = get_public_id_strategy()
        strategy2 = get_public_id_strategy()

        # Should return different instances
        assert strategy1 is not strategy2
        assert strategy1.id_resolver is not strategy2.id_resolver
        assert strategy1.graphql_resolver is not strategy2.graphql_resolver
        assert strategy1.queryset_annotator is not strategy2.queryset_annotator


@pytest.mark.django_db
class TestGetHashidsStrategyFromInstanceOrCls:
    def test_returns_public_id_strategy_for_public_id_model_when_enabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_returns_public_id_strategy_for_public_id_model_class_when_enabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            strategy = get_hashids_strategy_from_instance_or_cls(DummyPublicIdModel)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, PublicIdQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_public_id_model_when_disabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=False
        ):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_when_enabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyLegacyModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_when_disabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=False
        ):
            dummy_instance = DummyLegacyModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy, HashidsStrategyBundle)
            assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)
            assert isinstance(strategy.queryset_annotator, LegacyQuerysetAnnotatorStrategy)

    def test_returns_legacy_strategy_for_legacy_model_class(self) -> None:
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
    def test_uses_public_id_strategy_when_enabled(self) -> None:
        with patch(
            "baseapp_core.hashids.strategies._is_public_id_logic_enabled", return_value=True
        ):
            dummy_instance = DummyPublicIdModelFactory()

            result = graphql_to_global_id_using_strategy(
                dummy_instance, "DummyPublicIdModel", dummy_instance.pk
            )

            assert result == str(dummy_instance.public_id)

    def test_uses_legacy_strategy_when_disabled(self) -> None:
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
class TestHashidsStrategyIntegrationScenarios:
    def test_public_id_model_with_public_id_logic_enabled_uses_public_id_strategy(self) -> None:
        with override_settings(ENABLE_PUBLIC_ID_LOGIC=True):
            dummy_instance = DummyPublicIdModelFactory()
            strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

            assert isinstance(strategy.id_resolver, PublicIdResolverStrategy)
            assert isinstance(strategy.graphql_resolver, PublicIdGraphQLResolverStrategy)

            resolved_id = strategy.id_resolver.get_id_from_instance(dummy_instance)
            assert resolved_id == dummy_instance.public_id

            resolved_instance = strategy.id_resolver.resolve_id(dummy_instance.public_id)
            assert resolved_instance.pk == dummy_instance.pk

    def test_public_id_model_with_public_id_logic_disabled_uses_legacy_strategy(self) -> None:
        with override_settings(ENABLE_PUBLIC_ID_LOGIC=False):
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

    def test_legacy_model_always_uses_legacy_strategy(self) -> None:
        for config_value in [True, False, None, ""]:
            with override_settings(ENABLE_PUBLIC_ID_LOGIC=config_value):
                dummy_instance = DummyLegacyModelFactory()
                strategy = get_hashids_strategy_from_instance_or_cls(dummy_instance)

                assert isinstance(strategy.id_resolver, LegacyIdResolverStrategy)
                assert isinstance(strategy.graphql_resolver, LegacyGraphQLResolverStrategy)

                resolved_id = strategy.id_resolver.get_id_from_instance(dummy_instance)
                assert resolved_id == dummy_instance.pk

    def test_mixed_strategy_usage_in_same_test(self) -> None:
        public_id_instance = DummyPublicIdModelFactory()
        legacy_instance = DummyLegacyModelFactory()

        with override_settings(ENABLE_PUBLIC_ID_LOGIC=True):
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
