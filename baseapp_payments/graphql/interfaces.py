from typing import TYPE_CHECKING

import graphene

from baseapp_core.graphql import get_object_type_for_model

from ..models import (
    CARD_HOLD_PREFETCH_PATH,
    NOT_PREFETCHED,
    get_card_hold_model,
    prefetched_card_hold,
)
from ..permissions import owns_or_oversees_card_hold

if TYPE_CHECKING:
    from query_optimizer.compiler import OptimizationCompiler

    from ..models import AbstractCardHold


def _card_hold_optimizer_hook(compiler: "OptimizationCompiler") -> None:
    """Prefetch the targets' holds through ``document__card_hold`` when ``cardHold`` is
    selected, so a page of targets costs two batched queries instead of one per row."""
    from query_optimizer.optimizer import QueryOptimizer

    parent = compiler.optimizer
    if parent is None or parent.model is None:
        return
    if CARD_HOLD_PREFETCH_PATH in parent.prefetch_related:
        return
    CardHold = get_card_hold_model()
    hold_optimizer = QueryOptimizer(
        model=CardHold,
        info=compiler.info,
        name=CARD_HOLD_PREFETCH_PATH,
        parent=parent,
    )
    # "id" gates the relay-id annotation (see compose-a-block §8). The rest of the row is
    # loaded too: this optimizer is built by hand, so it doesn't know which hold fields
    # the query selected, and deferring them would cost a query per field per row. It is
    # one row per target, so loading it whole is cheap.
    hold_optimizer.only_fields.append("id")
    hold_optimizer.only_fields.extend(
        field.attname for field in CardHold._meta.concrete_fields if field.attname != "id"
    )
    parent.prefetch_related[CARD_HOLD_PREFETCH_PATH] = hold_optimizer


class CardHoldsInterface(graphene.Interface):
    """Adds ``cardHold`` to a target's ObjectType: the hold backing it, if the viewer may
    see it.

    All optimizer wiring lives on the field: consumers add nothing to their own
    ``pre_optimization_hook``. The target model needs ``DocumentIdMixin`` (its
    ``document`` GenericRelation is the prefetch path).
    """

    card_hold = graphene.Field(
        lambda: get_object_type_for_model(get_card_hold_model())(),
        description="The card hold backing this object; null when none, or not yours.",
    )
    card_hold.optimizer_hook = _card_hold_optimizer_hook

    def resolve_card_hold(self, info: graphene.ResolveInfo) -> "AbstractCardHold | None":
        if getattr(self, "pk", None) is None:
            return None
        hold = prefetched_card_hold(self)
        if hold is NOT_PREFETCHED:
            hold = get_card_hold_model().objects.for_target(self).first()
        # The view_cardhold rule itself, not has_perm(perm, hold): an owner costs nothing,
        # and the model-level grant is looked up once per request, not once per row.
        if hold is None or not owns_or_oversees_card_hold(info.context.user, hold):
            return None
        return hold


def get_card_holds_interface() -> type[CardHoldsInterface]:
    return CardHoldsInterface
