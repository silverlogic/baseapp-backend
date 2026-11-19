"""The staff decision mutations on a failed deferred hold (cardHoldKeep, cardHoldCancel),
through the test project's schema, where the plugin registers them."""

from typing import Any

import pytest
import swapper
from django.contrib.auth.models import AnonymousUser, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.utils import timezone

from baseapp_core.graphql import get_obj_relay_id
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db

KEEP = """
    mutation($input: CardHoldKeepInput!) {
        cardHoldKeep(input: $input) { cardHold { id status kept failureReason } }
    }
"""
CANCEL = """
    mutation($input: CardHoldCancelInput!) {
        cardHoldCancel(input: $input) { cardHold { id status kept } }
    }
"""


def run(query: str, user: Any, hold: Any) -> Any:
    from testproject.graphql import schema

    request = RequestFactory().post("/graphql")
    request.user = user or AnonymousUser()
    return schema.execute(
        query,
        variable_values={"input": {"id": get_obj_relay_id(hold)}},
        context_value=request,
    )


def grant(user: Any, codename: str) -> Any:
    user.user_permissions.add(
        Permission.objects.get(
            codename=codename, content_type=ContentType.objects.get_for_model(CardHold)
        )
    )
    return type(user).objects.get(pk=user.pk)


@pytest.fixture
def decider(db) -> Any:
    """Staff granted change_cardhold (and view_cardhold, to read the payload back)."""
    return grant(grant(UserFactory(is_staff=True), "change_cardhold"), "view_cardhold")


@pytest.fixture
def failed_hold(holder) -> Any:
    return CardHoldFactory(
        target=HoldableOrderFactory(user=holder),
        status=CardHold.Status.FAILED,
        failed_at=timezone.now(),
        failure_code="card_declined",
    )


def error_code(result: Any) -> str:
    assert result.errors, result.data
    return result.errors[0].extensions["code"]


class TestKeep:
    def test_staff_with_change_cardhold_keep_it(self, failed_hold, decider) -> None:
        result = run(KEEP, decider, failed_hold)

        assert result.errors is None, result.errors
        assert result.data["cardHoldKeep"]["cardHold"] == {
            "id": get_obj_relay_id(failed_hold),
            "status": "failed",
            "kept": True,
            "failureReason": "card_declined",
        }
        failed_hold.refresh_from_db()
        assert failed_hold.kept_by == decider

    def test_keeping_twice_is_an_invalid_action(self, failed_hold, decider) -> None:
        run(KEEP, decider, failed_hold)

        assert error_code(run(KEEP, decider, failed_hold)) == "invalid_action"
        assert error_code(run(CANCEL, decider, failed_hold)) == "invalid_action"


class TestCancel:
    def test_staff_with_change_cardhold_cancel_it(self, failed_hold, decider) -> None:
        result = run(CANCEL, decider, failed_hold)

        assert result.errors is None, result.errors
        assert result.data["cardHoldCancel"]["cardHold"]["status"] == "released"
        assert failed_hold.target.__class__.objects.get(pk=failed_hold.target.pk).status == (
            HoldableOrder.Status.CANCELLED
        )

    def test_a_hold_that_isnt_failed_is_an_invalid_action(self, holder, decider) -> None:
        hold = CardHoldFactory(target=HoldableOrderFactory(user=holder))

        assert error_code(run(CANCEL, decider, hold)) == "invalid_action"
        hold.refresh_from_db()
        assert hold.status == CardHold.Status.AUTHORIZED


class TestPermissions:
    @pytest.mark.parametrize("query", [KEEP, CANCEL], ids=["keep", "cancel"])
    def test_the_customer_cant_decide_their_own_hold(self, failed_hold, holder, query) -> None:
        assert error_code(run(query, holder, failed_hold)) == "permission_required"
        failed_hold.refresh_from_db()
        assert failed_hold.status == CardHold.Status.FAILED and failed_hold.kept_at is None

    @pytest.mark.parametrize("query", [KEEP, CANCEL], ids=["keep", "cancel"])
    def test_staff_status_or_view_cardhold_alone_isnt_enough(self, failed_hold, query) -> None:
        viewer = grant(UserFactory(is_staff=True), "view_cardhold")

        assert error_code(run(query, UserFactory(is_staff=True), failed_hold)) == (
            "permission_required"
        )
        assert error_code(run(query, viewer, failed_hold)) == "permission_required"

    def test_anonymous_is_refused(self, failed_hold) -> None:
        result = run(KEEP, None, failed_hold)

        assert result.errors
        failed_hold.refresh_from_db()
        assert failed_hold.kept_at is None

    def test_a_superuser_may_decide(self, failed_hold) -> None:
        result = run(KEEP, UserFactory(is_superuser=True, is_staff=True), failed_hold)

        assert result.errors is None, result.errors

    def test_an_id_that_isnt_a_card_hold_is_refused_like_a_forbidden_one(
        self, holder, decider, caplog
    ) -> None:
        from testproject.graphql import schema

        request = RequestFactory().post("/graphql")
        request.user = decider
        with caplog.at_level("WARNING", logger="baseapp_payments.graphql.mutations"):
            for bad_id in (get_obj_relay_id(holder), "not-an-id"):
                result = schema.execute(
                    KEEP, variable_values={"input": {"id": bad_id}}, context_value=request
                )
                assert error_code(result) == "permission_required"

        # A malformed id is the client's mistake: a warning, with no traceback.
        resolved = [r for r in caplog.records if "Could not resolve card hold id" in r.message]
        assert resolved and all(r.levelname == "WARNING" and r.exc_info is None for r in resolved)

    def test_change_cardhold_is_a_model_level_grant_answered_per_hold(
        self, failed_hold, holder, decider
    ) -> None:
        perm = f"{CardHold._meta.app_label}.change_cardhold"

        assert decider.has_perm(perm, failed_hold)
        assert not holder.has_perm(perm, failed_hold)
        assert not decider.has_perm(perm, failed_hold.target)  # not a hold
        assert not AnonymousUser().has_perm(perm, failed_hold)

    def test_without_card_holds_the_backend_ignores_change_cardhold(
        self, failed_hold, decider
    ) -> None:
        from unittest.mock import patch

        from baseapp_payments import permissions

        with patch.object(permissions, "card_holds_enabled", return_value=False):
            assert (
                permissions.has_card_hold_perm(decider, "payments.change_cardhold", failed_hold)
                is None
            )


def test_the_mutations_module_adds_nothing_without_card_holds(settings) -> None:
    import importlib.util
    from pathlib import Path

    from baseapp_payments.graphql import mutations

    settings.BASEAPP_PAYMENTS_CARDHOLD_MODEL = "baseapp_payments.CardHold"  # the default
    path = Path(mutations.__file__)
    spec = importlib.util.spec_from_file_location("baseapp_payments.graphql._disabled_m", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)

    assert not hasattr(loaded, "CardHoldKeep")
    assert [name for name in vars(loaded.CardHoldMutations) if not name.startswith("_")] == []


def test_the_decision_mixin_needs_a_decision() -> None:
    from baseapp_payments.graphql.mutations import CardHoldDecisionMixin

    with pytest.raises(NotImplementedError):
        CardHoldDecisionMixin.decide(1, None)
