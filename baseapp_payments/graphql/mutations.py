"""Staff decisions on a card hold: retry a failed deferred hold, keep or cancel its
target, or mark a partially paid target paid outside the app.

All four need ``change_cardhold`` on the hold (a model-level grant: the hold's own customer
never has it; see ``permissions.can_decide_card_hold``). Registered by the plugin; without
a card hold model ``CardHoldMutations`` adds nothing.
"""

import logging
from typing import Any

import graphene
from django.utils.translation import gettext_lazy as _
from graphql.error import GraphQLError

from baseapp_core.graphql import (
    RelayMutation,
    get_obj_from_relay_id,
    get_object_type_for_model,
    login_required,
)

from ..models import card_holds_enabled, get_card_hold_model
from ..permissions import can_decide_card_hold

logger = logging.getLogger(__name__)


def _decided_hold(info: graphene.ResolveInfo, relay_id: str) -> Any:
    """The hold behind ``relay_id`` when the viewer may decide it; a permission error
    otherwise, the same for a hold that doesn't exist, so ids can't be probed."""
    try:
        hold = get_obj_from_relay_id(info, relay_id)
    # A malformed id is the client's mistake, not ours: logged at warning, no traceback.
    # ast-grep-ignore: exception-handling-without-logging
    except Exception:
        logger.warning("Could not resolve card hold id %r", relay_id)
        hold = None
    if not isinstance(hold, get_card_hold_model()) or not can_decide_card_hold(
        info.context.user, hold
    ):
        raise GraphQLError(
            str(_("You don't have permission to perform this action")),
            extensions={"code": "permission_required"},
        )
    return hold


def _not_failed() -> GraphQLError:
    return GraphQLError(
        str(_("Only a failed card hold that wasn't kept can be decided.")),
        extensions={"code": "invalid_action"},
    )


class CardHoldDecisionMixin:
    """The input and payload both decisions share."""

    class Input:
        id = graphene.ID(required=True, description="The failed card hold.")

    @classmethod
    def decide(cls, card_hold_id: int, actor: Any) -> bool:
        raise NotImplementedError

    @classmethod
    def refused(cls) -> GraphQLError:
        return _not_failed()

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root: Any, info: graphene.ResolveInfo, **input: Any) -> Any:
        hold = _decided_hold(info, input["id"])
        if not cls.decide(hold.pk, info.context.user):
            raise cls.refused()
        hold.refresh_from_db()
        return cls(card_hold=hold)


def _retry_refused(refusal: Any) -> GraphQLError:
    """The error for a retry that placed nothing; ``extensions.reason`` says why."""
    messages = {
        "no_retries_left": _("This card hold has no retries left. Keep it or cancel it."),
        "date_passed": _("The target's date has come, so it can't take a hold any more."),
        "not_holdable": _("The target can't take a hold any more."),
        "unavailable": _("Card holds can't be placed right now."),
    }
    reason = getattr(refusal, "value", refusal)
    message = messages.get(reason, _("Only a failed card hold that wasn't kept can be retried."))
    return GraphQLError(str(message), extensions={"code": "invalid_action", "reason": reason})


if card_holds_enabled():
    from ..holds import (
        cancel_failed_hold,
        keep_failed_hold,
        mark_paid_outside,
        retry_failed_hold,
    )

    CardHoldObjectType = get_object_type_for_model(get_card_hold_model())

    class CardHoldRetry(RelayMutation):
        """Retry a failed deferred hold on the same saved card, as a new off-session
        attempt. The returned cardHold.status is the outcome: authorized; failed (staff
        are told again, one retry fewer is left); pending (no answer from Stripe yet,
        settled later); or scheduled (the target's date moved past the hold window, so it
        is placed on holdOn, like any scheduled hold). Refused with an invalid_action
        error whose extensions.reason says why (not_failed, no_retries_left, date_passed,
        not_holdable or unavailable): a hold that isn't failed, was kept or cancelled,
        has no retries left, or whose target can't take a hold. Needs change_cardhold."""

        card_hold = graphene.Field(CardHoldObjectType)

        class Input:
            id = graphene.ID(required=True, description="The failed card hold.")

        @classmethod
        @login_required
        def mutate_and_get_payload(
            cls, root: Any, info: graphene.ResolveInfo, **input: Any
        ) -> "CardHoldRetry":
            hold = _decided_hold(info, input["id"])
            result = retry_failed_hold(hold.pk, info.context.user)
            if result.refusal is not None:
                raise _retry_refused(result.refusal)
            hold.refresh_from_db()
            return cls(card_hold=hold)

    class CardHoldKeep(CardHoldDecisionMixin, RelayMutation):
        """Keep the target of a failed deferred hold: it closes later by a fresh charge
        of the card, like a target with no hold. Final."""

        card_hold = graphene.Field(CardHoldObjectType)

        class Input(CardHoldDecisionMixin.Input):
            pass

        @classmethod
        def decide(cls, card_hold_id: int, actor: Any) -> bool:
            return keep_failed_hold(card_hold_id, actor)

    class CardHoldCancel(CardHoldDecisionMixin, RelayMutation):
        """Cancel the target of a failed deferred hold (through its adapter's ``cancel``);
        nothing is charged."""

        card_hold = graphene.Field(CardHoldObjectType)

        class Input(CardHoldDecisionMixin.Input):
            pass

        @classmethod
        def decide(cls, card_hold_id: int, actor: Any) -> bool:
            return cancel_failed_hold(card_hold_id, actor)

    class CardHoldMarkPaid(CardHoldDecisionMixin, RelayMutation):
        """Record the rest of a partially paid target (its hold captured, the difference
        above it declined) as paid outside the app: its payment status becomes paid, and
        the difference is never charged again."""

        card_hold = graphene.Field(CardHoldObjectType)

        class Input:
            id = graphene.ID(required=True, description="The partially paid card hold.")

        @classmethod
        def decide(cls, card_hold_id: int, actor: Any) -> bool:
            return mark_paid_outside(card_hold_id, actor)

        @classmethod
        def refused(cls) -> GraphQLError:
            return GraphQLError(
                str(
                    _(
                        "Only a partially paid card hold that isn't being charged can be marked paid."
                    )
                ),
                extensions={"code": "invalid_action"},
            )

    class CardHoldMutations:
        card_hold_retry = CardHoldRetry.Field()
        card_hold_keep = CardHoldKeep.Field()
        card_hold_cancel = CardHoldCancel.Field()
        card_hold_mark_paid = CardHoldMarkPaid.Field()

else:

    class CardHoldMutations:  # type: ignore[no-redef]
        pass
