from typing import Any

from constance import config

from baseapp_core.hashids.models import LegacyWithPkMixin, PublicIdMixin
from baseapp_core.hashids.strategies.bundle import HashidsStrategyBundle
from baseapp_core.hashids.utils import has_autoincrement_pk, is_uuid4


def _is_public_id_logic_enabled() -> bool:
    return bool(config.ENABLE_PUBLIC_ID_LOGIC)


def _is_model_public_id_compatible(model_cls: type) -> bool:
    """
    These are the constraints for a model to be compatible with the public ID feature.
    - It must extend PublicIdMixin.
    - It must have an auto-incrementing primary key.
    """
    return issubclass(model_cls, PublicIdMixin) and has_autoincrement_pk(model_cls)


def _is_model_pk_compatible(model_cls: type) -> bool:
    return issubclass(model_cls, LegacyWithPkMixin)


def get_legacy_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.legacy import (
        LegacyGraphQLResolverStrategy,
        LegacyIdResolverStrategy,
        LegacyQuerysetAnnotatorStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=LegacyIdResolverStrategy,
        graphql_resolver=LegacyGraphQLResolverStrategy,
        queryset_annotator=LegacyQuerysetAnnotatorStrategy,
    )


def get_public_id_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.public_id import (
        PublicIdGraphQLResolverStrategy,
        PublicIdQuerysetAnnotatorStrategy,
        PublicIdResolverStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=PublicIdResolverStrategy,
        graphql_resolver=PublicIdGraphQLResolverStrategy,
        queryset_annotator=PublicIdQuerysetAnnotatorStrategy,
    )


def get_pk_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.legacy import (
        LegacyIdResolverStrategy,
        LegacyQuerysetAnnotatorStrategy,
    )
    from baseapp_core.hashids.strategies.pk import PkGraphQLResolverStrategy

    return HashidsStrategyBundle(
        id_resolver=LegacyIdResolverStrategy,
        graphql_resolver=PkGraphQLResolverStrategy,
        queryset_annotator=LegacyQuerysetAnnotatorStrategy,
    )


def get_hashids_strategy_from_instance_or_cls(instance_or_cls: Any) -> HashidsStrategyBundle:
    model_cls = instance_or_cls if isinstance(instance_or_cls, type) else instance_or_cls.__class__

    if _is_model_public_id_compatible(model_cls) and _is_public_id_logic_enabled():
        return get_public_id_strategy()

    if _is_model_pk_compatible(model_cls):
        return get_pk_strategy()

    return get_legacy_strategy()


def graphql_to_global_id_using_strategy(model_instance, type_, id) -> str:
    if _is_model_public_id_compatible(model_instance.__class__) and _is_public_id_logic_enabled():
        strategy = get_hashids_strategy_from_instance_or_cls(model_instance)
        if global_id := strategy.graphql_resolver.to_global_id(model_instance, type_, id):
            return global_id

    return get_legacy_strategy().graphql_resolver.to_global_id(model_instance, type_, id)


def graphql_get_node_from_global_id_using_strategy(info, global_id, only_type=None) -> Any:
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        public_id_strategy = get_public_id_strategy()
        try:
            node = public_id_strategy.graphql_resolver.get_node_from_global_id(
                info, global_id, only_type
            )
            if _is_model_public_id_compatible(node.__class__):
                return node
            raise Exception(f"{node.__class__} is not compatible with the Public ID strategy")
        except public_id_strategy.graphql_resolver.NoInstanceFound:
            pass

    if global_id.isdigit():
        pk_strategy = get_pk_strategy()
        try:
            node = pk_strategy.graphql_resolver.get_node_from_global_id(info, global_id, only_type)
            if _is_model_pk_compatible(node.__class__):
                return node
            raise Exception(f"{node.__class__.__name__} is not compatible with the PK strategy")
        except pk_strategy.graphql_resolver.NoInstanceFound:
            pass

    legacy_strategy = get_legacy_strategy()
    return legacy_strategy.graphql_resolver.get_node_from_global_id(info, global_id, only_type)


def graphql_get_pk_from_global_id_using_strategy(global_id):
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        strategy = get_public_id_strategy()
    else:
        strategy = get_legacy_strategy()

    return strategy.graphql_resolver.get_pk_from_global_id(global_id)


def graphql_get_instance_from_global_id_using_strategy(info, global_id, get_node=False):
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        strategy = get_public_id_strategy()
    else:
        strategy = get_legacy_strategy()

    return strategy.graphql_resolver.get_instance_from_global_id(info, global_id, get_node)
