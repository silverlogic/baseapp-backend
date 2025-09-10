from typing import Any

from constance import config

from baseapp_core.graphql.utils import get_model_from_graphql_object_type
from baseapp_core.hashids.models import PublicIdMixin
from baseapp_core.hashids.strategies.bundle import HashidsStrategyBundle
from baseapp_core.hashids.utils import is_uuid4


def _is_public_id_logic_enabled() -> bool:
    return bool(config.ENABLE_PUBLIC_ID_LOGIC)


def get_legacy_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.legacy.graphql_resolver import (
        LegacyGraphQLResolverStrategy,
    )
    from baseapp_core.hashids.strategies.legacy.id_resolver import (
        LegacyIdResolverStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=LegacyIdResolverStrategy, graphql_resolver=LegacyGraphQLResolverStrategy
    )


def get_public_id_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.public_id.graphql_resolver import (
        PublicIdGraphQLResolverStrategy,
    )
    from baseapp_core.hashids.strategies.public_id.id_resolver import (
        PublicIdResolverStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=PublicIdResolverStrategy, graphql_resolver=PublicIdGraphQLResolverStrategy
    )


def get_hashids_strategy_from_instance_or_cls(instance_or_cls: Any) -> HashidsStrategyBundle:
    model_cls = instance_or_cls if isinstance(instance_or_cls, type) else instance_or_cls.__class__
    is_public_id_compatible = issubclass(model_cls, PublicIdMixin)

    if is_public_id_compatible and _is_public_id_logic_enabled():
        return get_public_id_strategy()

    return get_legacy_strategy()


def graphql_to_global_id_using_strategy(type_, id) -> str:
    if _is_public_id_logic_enabled():
        type_model = get_model_from_graphql_object_type(type_)
        strategy = get_hashids_strategy_from_instance_or_cls(type_model)
        return strategy.graphql_resolver.to_global_id(type_, id)

    return get_legacy_strategy().graphql_resolver.to_global_id(type_, id)


def graphql_get_node_from_global_id_using_strategy(info, global_id, only_type=None) -> Any:
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        public_id_strategy = get_public_id_strategy()
        if node := public_id_strategy.graphql_resolver.get_node_from_global_id(
            info, global_id, only_type
        ):
            return node

    legacy_strategy = get_legacy_strategy()
    return legacy_strategy.graphql_resolver.get_node_from_global_id(info, global_id, only_type)


def graphql_get_pk_from_global_id_using_strategy(global_id):
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        public_id_strategy = get_public_id_strategy()
        if pk := public_id_strategy.graphql_resolver.get_pk_from_global_id(global_id):
            return pk

    return get_legacy_strategy().graphql_resolver.get_pk_from_global_id(global_id)
