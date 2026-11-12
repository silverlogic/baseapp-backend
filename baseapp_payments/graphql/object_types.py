import datetime
from typing import Any

import graphene

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

from ..models import card_holds_enabled, get_card_hold_model
from ..permissions import can_view_card_hold, sees_card_hold_details


class BaseCardHoldObjectType:
    """A card hold as its customer, or a user granted ``view_cardhold``, sees it.

    A customer never sees why a deferred hold failed: ``failed`` reads as ``scheduled``,
    ``kept`` as false and ``failureReason`` as null. Staff see all three as they are.
    """

    status = graphene.String(
        required=True,
        description="pending, authorized, released, captured, scheduled, failed or saved.",
    )
    amount_cents = graphene.Int(required=True, description="The amount authorized, in cents.")
    estimated_amount_cents = graphene.Int(
        required=True, description="The target's estimated price, before the buffer, in cents."
    )
    expires_at = graphene.DateTime(description="When Stripe stops honouring the hold.")
    brand = graphene.String(description="The card brand, e.g. visa.")
    last4 = graphene.String(description="The card's last four digits.")
    hold_on = graphene.Date(
        description=(
            "For a hold scheduled for later: the day it will be placed. Null otherwise, or"
            " when the target has no date."
        )
    )
    kept = graphene.Boolean(
        required=True,
        description="Staff only: whether staff kept the target despite a failed hold.",
    )
    failure_reason = graphene.String(
        description="Staff only: Stripe's code for why a deferred hold failed."
    )
    payment_status = graphene.String(
        required=True,
        description=(
            "How much of the final amount was taken: unpaid, paid, or partially_paid (the"
            " hold was captured and the difference above it was declined)."
        ),
    )

    class Meta:
        # The model is set on the concrete type below, only when card holds are enabled,
        # so this module imports cleanly for a project that doesn't use them.
        interfaces = (RelayNode,)
        fields = ("id",)
        description = "A card authorization backing a target, captured or released later."

    @classmethod
    def get_node(cls, info: graphene.ResolveInfo, id: str) -> Any:
        node = super().get_node(info, id)
        if node is None or not can_view_card_hold(info.context.user, node):
            return None
        return node

    def resolve_status(self, info: graphene.ResolveInfo) -> str:
        if self.status == self.Status.FAILED and not sees_card_hold_details(info.context.user):
            return self.Status.SCHEDULED
        return self.status

    def resolve_brand(self, info: graphene.ResolveInfo) -> str | None:
        return self.card_brand or None

    def resolve_last4(self, info: graphene.ResolveInfo) -> str | None:
        return self.card_last4 or None

    def resolve_hold_on(self, info: graphene.ResolveInfo) -> datetime.date | None:
        # The stored day, the one the sweep places it on: no target read, no query.
        if self.status not in (self.Status.SCHEDULED, self.Status.FAILED):
            return None
        return self.hold_on

    def resolve_kept(self, info: graphene.ResolveInfo) -> bool:
        return sees_card_hold_details(info.context.user) and self.kept_at is not None

    def resolve_failure_reason(self, info: graphene.ResolveInfo) -> str | None:
        if not sees_card_hold_details(info.context.user):
            return None
        return self.failure_code or None


if card_holds_enabled():

    class CardHoldObjectType(BaseCardHoldObjectType, DjangoObjectType):
        class Meta(BaseCardHoldObjectType.Meta):
            model = get_card_hold_model()
