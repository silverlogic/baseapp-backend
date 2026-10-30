from typing import TYPE_CHECKING, Any, Optional, Type

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.models import F, QuerySet

from baseapp_core.hashids.models import LegacyWithPkMixin
from baseapp_core.hashids.strategies.bundle import HashidsStrategyBundle
from baseapp_core.hashids.utils import is_uuid4
from baseapp_core.models import DocumentIdMixin
from baseapp_core.utils import has_autoincrement_pk

if TYPE_CHECKING:
    from django.db.models import Model


def _is_public_id_logic_enabled() -> bool:
    """`settings.ENABLE_PUBLIC_ID_LOGIC` (default True).

    A deployment-level choice that never changes while the app runs, so it is a Django setting:
    it is read for every ID resolved or rendered, and a setting costs no cache or database trip.
    """
    return bool(getattr(settings, "ENABLE_PUBLIC_ID_LOGIC", True))


def is_public_id_pk_lookup_allowed() -> bool:
    """`settings.BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP` (default True).

    Whether REST lookups, fields and filters still accept the integer pk of a model that uses
    the public id strategy. Turn it off once clients only send public ids, so pks can no longer
    be enumerated. Models without public ids always accept their pk.
    """
    return bool(getattr(settings, "BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP", True))


def _is_model_public_id_compatible(model_cls: type) -> bool:
    """
    These are the constraints for a model to be compatible with the public ID feature.
    - It must extend DocumentIdMixin.
    - It must have an auto-incrementing primary key.
    """
    return issubclass(model_cls, DocumentIdMixin) and has_autoincrement_pk(model_cls)


def _is_model_pk_compatible(model_cls: type) -> bool:
    return issubclass(model_cls, LegacyWithPkMixin)


def get_legacy_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.legacy import (
        LegacyDRFResolverStrategy,
        LegacyGraphQLResolverStrategy,
        LegacyIdResolverStrategy,
        LegacyQuerysetAnnotatorStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=LegacyIdResolverStrategy,
        graphql_resolver=LegacyGraphQLResolverStrategy,
        queryset_annotator=LegacyQuerysetAnnotatorStrategy,
        drf_resolver=LegacyDRFResolverStrategy,
    )


def get_public_id_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.public_id import (
        PublicIdDRFResolverStrategy,
        PublicIdGraphQLResolverStrategy,
        PublicIdQuerysetAnnotatorStrategy,
        PublicIdResolverStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=PublicIdResolverStrategy,
        graphql_resolver=PublicIdGraphQLResolverStrategy,
        queryset_annotator=PublicIdQuerysetAnnotatorStrategy,
        drf_resolver=PublicIdDRFResolverStrategy,
    )


def get_pk_strategy() -> HashidsStrategyBundle:
    from baseapp_core.hashids.strategies.legacy import (
        LegacyIdResolverStrategy,
        LegacyQuerysetAnnotatorStrategy,
    )
    from baseapp_core.hashids.strategies.pk import (
        PkDRFResolverStrategy,
        PkGraphQLResolverStrategy,
    )

    return HashidsStrategyBundle(
        id_resolver=LegacyIdResolverStrategy,
        graphql_resolver=PkGraphQLResolverStrategy,
        queryset_annotator=LegacyQuerysetAnnotatorStrategy,
        drf_resolver=PkDRFResolverStrategy,
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
    # Clients send `node(id: "")` while the id they'd look up isn't known yet (e.g.
    # `currentProfile?.id || ''`). An empty id names no node, so resolve it to null like a
    # missing one instead of raising "Unable to parse global ID" from the legacy strategy.
    if not global_id:
        return None

    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        public_id_strategy = get_public_id_strategy()
        try:
            node = public_id_strategy.graphql_resolver.get_node_from_global_id(
                info, global_id, only_type
            )
            if node is None:
                return None
            if _is_model_public_id_compatible(node.__class__):
                return node
            raise Exception(f"{node.__class__} is not compatible with the Public ID strategy")
        except public_id_strategy.graphql_resolver.NoInstanceFound:
            pass

    if global_id.isdigit():
        pk_strategy = get_pk_strategy()
        try:
            node = pk_strategy.graphql_resolver.get_node_from_global_id(info, global_id, only_type)
            if node is None:
                return None
            if _is_model_pk_compatible(node.__class__):
                return node
            raise Exception(f"{node.__class__.__name__} is not compatible with the PK strategy")
        except pk_strategy.graphql_resolver.NoInstanceFound:
            pass

    legacy_strategy = get_legacy_strategy()
    return legacy_strategy.graphql_resolver.get_node_from_global_id(info, global_id, only_type)


def graphql_get_pk_from_global_id_using_strategy(global_id) -> int | str:
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        strategy = get_public_id_strategy()
    else:
        strategy = get_legacy_strategy()

    return strategy.graphql_resolver.get_pk_from_global_id(global_id)


def graphql_get_instance_from_global_id_using_strategy(info, global_id, get_node=False) -> "Model":
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        strategy = get_public_id_strategy()
    else:
        strategy = get_legacy_strategy()

    return strategy.graphql_resolver.get_instance_from_global_id(info, global_id, get_node)


def drf_get_pk_from_public_id_using_strategy(
    value: Any, expected_model: Optional[Type] = None
) -> int | str:
    if is_uuid4(value) and _is_public_id_logic_enabled():
        strategy = get_public_id_strategy()
    else:
        strategy = get_legacy_strategy()

    return strategy.drf_resolver.resolve_public_id_to_pk(value, expected_model=expected_model)


def should_use_public_id(model_cls: type) -> bool:
    return _is_model_public_id_compatible(model_cls) and _is_public_id_logic_enabled()


def drf_get_pk_from_public_id_or_pk(
    value: Any, model_cls: type, *, allow_pk_lookup: bool | None = None
) -> Any | None:
    """Return the pk to look a `model_cls` row up by, or None when `value` cannot be one of its ids.

    For a model that uses the public id strategy, `value` must be the public id of a `model_cls`
    row (another model's public id gives None), or its integer pk while pk lookups are allowed
    (`allow_pk_lookup`, which defaults to `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP`). For any other
    model, `value` is returned as-is: it is the raw pk, and the caller's pk lookup validates it.
    It does not check that the row exists.
    """
    from baseapp_core.hashids.strategies.interfaces import DRFResolverStrategy

    if value is None or isinstance(value, bool):
        return None
    if not should_use_public_id(model_cls):
        return value
    if is_uuid4(value):
        try:
            return drf_get_pk_from_public_id_using_strategy(str(value), expected_model=model_cls)
        except DRFResolverStrategy.NoInstanceFound:
            return None
    if allow_pk_lookup is None:
        allow_pk_lookup = is_public_id_pk_lookup_allowed()
    if allow_pk_lookup and str(value).isascii() and str(value).isdigit():
        return int(value)
    return None


def _get_related_model_for_path(model_cls: type, path: str) -> type:
    """Follow a `__`-separated path of to-one relations and return the model it ends on."""
    current = model_cls
    for name in path.split("__"):
        field = current._meta.get_field(name)
        is_to_one = field.is_relation and (field.many_to_one or field.one_to_one)
        if not is_to_one or field.related_model is None:
            raise ValueError(
                f"annotate_public_ids: '{path}' must be a path of foreign keys or one-to-one "
                f"fields, but '{name}' on {current.__name__} is not one."
            )
        current = field.related_model
    return current


def annotate_public_ids(queryset: QuerySet, *fk_paths: str, include_self: bool = True) -> QuerySet:
    """Load public ids in the queryset itself, so serializing a list costs no query per row.

    - The queryset's own rows get `mapped_public_id` (unless `include_self=False`, or it is
      already annotated). `DocumentIdMixin.public_id` reads it.
    - Each foreign key path gets `<path>_public_id`, for example `annotate_public_ids(qs, "author",
      "post__author")` adds `author_public_id` and `post__author_public_id`.
      `PublicIdRelatedField` reads it through `get_annotated_public_id`, which also checks the
      `<prefix>_public_id_pk` annotations (the key of each relation on the path as loaded) so
      that it ignores the public id once a relation is reassigned, as an update does.

    Only models that use the public id strategy are annotated, so with `ENABLE_PUBLIC_ID_LOGIC =
    False`, or for a model without `DocumentIdMixin`, this adds nothing. Paths must follow
    foreign keys or one-to-one fields; for many-to-many or reverse relations, prefetch
    `"<relation>__document"` instead.
    """
    model_cls = queryset.model
    strategy = get_public_id_strategy()
    annotations: dict[str, Any] = {}

    if (
        include_self
        and should_use_public_id(model_cls)
        and "mapped_public_id" not in queryset.query.annotations
    ):
        annotations.update(strategy.queryset_annotator.get_annotations(model_cls))

    for path in fk_paths:
        related_model = _get_related_model_for_path(model_cls, path)
        alias = f"{path}_public_id"
        if should_use_public_id(related_model) and alias not in queryset.query.annotations:
            annotations.update(
                strategy.queryset_annotator.get_annotations(related_model, field=path, alias=alias)
            )
            # The key each relation on the path had when the row was loaded, so that
            # `get_annotated_public_id` can tell when the relation was reassigned since.
            names = path.split("__")
            for index in range(len(names)):
                prefix = "__".join(names[: index + 1])
                key_alias = _loaded_key_alias(prefix)
                if key_alias not in queryset.query.annotations:
                    annotations[key_alias] = F(prefix)

    return queryset.annotate(**annotations) if annotations else queryset


def _loaded_key_alias(path: str) -> str:
    return f"{path}_public_id_pk"


_MISSING = object()


def get_annotated_public_id(instance: "Model", path: str) -> Any | None:
    """The `<path>_public_id` that `annotate_public_ids` loaded on `instance`, or None.

    It is also None when the annotation may be stale: a relation on the path was reassigned on
    the instance after the row was loaded, for example by `serializer.save()` in an update.
    Callers then read the live relation instead.
    """
    public_id = instance.__dict__.get(f"{path}_public_id")
    if public_id is None:
        return None

    obj = instance
    names = path.split("__")
    for index, name in enumerate(names):
        loaded_key = instance.__dict__.get(
            _loaded_key_alias("__".join(names[: index + 1])), _MISSING
        )
        if loaded_key is _MISSING:
            return None
        try:
            field = obj._meta.get_field(name)
        except FieldDoesNotExist:
            return None
        is_cached = field.is_cached(obj)
        if field.concrete:
            current_key = obj.__dict__.get(field.attname, loaded_key)
        elif is_cached:
            related = field.get_cached_value(obj)
            current_key = related.pk if related is not None else None
        else:
            current_key = loaded_key
        if current_key != loaded_key:
            return None
        if not is_cached:
            # The rest of the path was never loaded on this instance, so nothing reassigned it.
            return public_id
        obj = field.get_cached_value(obj)
        if obj is None:
            return None
    return public_id
