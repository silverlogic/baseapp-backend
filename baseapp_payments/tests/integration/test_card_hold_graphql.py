"""The card hold GraphQL surface: CardHoldObjectType, CardHoldsInterface and the
mutation mixins. A small schema is built here around the test project's target."""

import datetime
import importlib.util
import uuid
from pathlib import Path
from typing import Any

import graphene
import pytest
import swapper
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_obj_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import graphql_shared_interfaces
from baseapp_payments.graphql import object_types as object_types_module
from baseapp_payments.graphql.interfaces import CardHoldsInterface
from baseapp_payments.graphql.mixins import (
    CardHoldPayloadMixin,
    CardHoldPaymentInputMixin,
    card_hold_payload,
)
from baseapp_payments.graphql.object_types import CardHoldObjectType
from baseapp_payments.holds import PlacementResult, PlacementStatus
from testproject.testapp.models import HoldableOrder

from ..factories import CardHoldFactory, HoldableOrderFactory, UserFactory

CardHold = swapper.load_model("baseapp_payments", "CardHold")

pytestmark = pytest.mark.django_db


class HoldableOrderObjectType(DjangoObjectType):
    class Meta:
        model = HoldableOrder
        fields = ("id",)
        interfaces = graphql_shared_interfaces.get(RelayNode, "CardHoldsInterface")


class Query(graphene.ObjectType):
    node = RelayNode.Field()
    # An optimized list path, to pin CardHoldsInterface.cardHold's optimizer hook.
    holdable_orders = DjangoConnectionField(HoldableOrderObjectType)


class HoldableOrderCreate(CardHoldPayloadMixin, graphene.relay.ClientIDMutation):
    class Input(CardHoldPaymentInputMixin):
        note = graphene.String()

    ok = graphene.Boolean()

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input) -> "HoldableOrderCreate":
        result = PlacementResult(
            PlacementStatus.REQUIRES_ACTION,
            client_secret="pi_1_secret",
            intent_type="payment_intent",
        )
        return cls(ok=bool(input.get("attempt_id")), **card_hold_payload(result))


class Mutation(graphene.ObjectType):
    holdable_order_create = HoldableOrderCreate.Field()


schema = graphene.Schema(
    query=Query, mutation=Mutation, types=[CardHoldObjectType, HoldableOrderObjectType]
)

HOLD_FIELDS = """
    status amountCents estimatedAmountCents expiresAt brand last4 holdOn kept failureReason
"""


def execute(query: str, user, **variables) -> dict:
    request = RequestFactory().post("/graphql")
    request.user = user or AnonymousUser()
    result = schema.execute(query, variable_values=variables, context_value=request)
    assert result.errors is None, result.errors
    return result.data


def hold_node(hold, user) -> dict | None:
    data = execute(
        f"query($id: ID!) {{ node(id: $id) {{ ... on CardHold {{ {HOLD_FIELDS} }} }} }}",
        user,
        id=get_obj_relay_id(hold),
    )
    return data["node"]


def order_card_hold(order, user) -> dict | None:
    data = execute(
        f"query($id: ID!) {{ node(id: $id) {{ ... on HoldableOrder {{ cardHold {{ {HOLD_FIELDS} }} }} }} }}",
        user,
        id=get_obj_relay_id(order),
    )
    return data["node"]["cardHold"]


def grant_view_cardhold(user) -> Any:
    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(
            codename="view_cardhold", content_type=ContentType.objects.get_for_model(CardHold)
        )
    )
    return type(user).objects.get(pk=user.pk)  # a fresh object: no cached perms


@pytest.fixture
def staff(db) -> Any:
    """A staff member granted ``view_cardhold``: staff status alone shows no one's holds."""
    return grant_view_cardhold(UserFactory(is_staff=True))


@pytest.fixture
def bare_staff(db) -> Any:
    return UserFactory(is_staff=True)


class TestCardHoldNode:
    def test_the_customer_sees_their_hold(self, order, holder) -> None:
        hold = CardHoldFactory(target=order)

        node = hold_node(hold, holder)

        assert node["status"] == "authorized"
        assert node["amountCents"] == 11_000
        assert node["estimatedAmountCents"] == 10_000
        assert node["brand"] == "visa" and node["last4"] == "4242"
        assert node["expiresAt"] is not None
        assert node["holdOn"] is None
        assert node["kept"] is False
        assert node["failureReason"] is None

    def test_someone_else_and_anonymous_see_nothing(self, order) -> None:
        hold = CardHoldFactory(target=order)

        assert hold_node(hold, UserFactory()) is None
        assert hold_node(hold, None) is None

    def test_staff_need_view_cardhold(self, order, staff, bare_staff) -> None:
        """N5: staff status alone shows nothing; the permission shows every hold."""
        hold = CardHoldFactory(target=order)

        assert hold_node(hold, bare_staff) is None
        assert hold_node(hold, staff)["status"] == "authorized"

    def test_a_failed_hold_reads_as_scheduled_for_the_customer(self, holder) -> None:
        order = HoldableOrderFactory(user=holder, target_date=datetime.date(2030, 3, 20))
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.FAILED,
            failure_code="card_declined",
            kept_at=datetime.datetime(2030, 3, 15, tzinfo=datetime.timezone.utc),
            card_brand="",
            card_last4="",
            hold_on=datetime.date(2030, 3, 15),
        )

        node = hold_node(hold, holder)

        assert node["status"] == "scheduled"
        assert node["kept"] is False
        assert node["failureReason"] is None
        assert node["holdOn"] == "2030-03-15"
        assert node["brand"] is None and node["last4"] is None

    def test_staff_see_the_failure(self, holder, staff) -> None:
        order = HoldableOrderFactory(user=holder)
        hold = CardHoldFactory(
            target=order,
            status=CardHold.Status.FAILED,
            failure_code="card_declined",
            kept_at=datetime.datetime(2030, 3, 15, tzinfo=datetime.timezone.utc),
        )

        node = hold_node(hold, staff)

        assert node["status"] == "failed"
        assert node["kept"] is True
        assert node["failureReason"] == "card_declined"
        assert node["holdOn"] is None  # never scheduled for a day

    def test_a_staff_customer_without_the_perm_sees_their_own_hold_as_a_customer(self) -> None:
        """m2: the details followed ``is_staff``, not ``view_cardhold``."""
        customer = UserFactory(is_staff=True)
        hold = CardHoldFactory(
            target=HoldableOrderFactory(user=customer),
            status=CardHold.Status.FAILED,
            failure_code="card_declined",
            kept_at=datetime.datetime(2030, 3, 15, tzinfo=datetime.timezone.utc),
        )

        node = hold_node(hold, customer)

        assert node["status"] == "scheduled"
        assert node["kept"] is False
        assert node["failureReason"] is None

    def test_a_grantee_who_isnt_staff_sees_the_failure(self, holder) -> None:
        hold = CardHoldFactory(
            target=HoldableOrderFactory(user=holder),
            status=CardHold.Status.FAILED,
            failure_code="card_declined",
        )

        node = hold_node(hold, grant_view_cardhold(UserFactory()))

        assert node["status"] == "failed" and node["failureReason"] == "card_declined"

    def test_hold_on_is_the_stored_day_the_sweep_uses(self, holder) -> None:
        """Not recomputed from the target: a later change of the window or the date
        shows only once reschedule() moved the hold itself."""
        order = HoldableOrderFactory(user=holder, target_date=datetime.date(2030, 3, 20))
        hold = CardHoldFactory(
            target=order, status=CardHold.Status.SCHEDULED, hold_on=datetime.date(2030, 3, 17)
        )

        assert hold_node(hold, holder)["holdOn"] == "2030-03-17"

    def test_only_scheduled_and_failed_holds_have_a_hold_on(self, holder) -> None:
        hold = CardHoldFactory(customer=holder, hold_on=datetime.date(2030, 3, 17))

        assert hold_node(hold, holder)["holdOn"] is None


class TestCardHoldsInterface:
    def test_the_target_exposes_its_hold_to_its_customer(self, order, holder) -> None:
        CardHoldFactory(target=order)

        assert order_card_hold(order, holder)["amountCents"] == 11_000

    def test_not_to_someone_else(self, order, staff, bare_staff) -> None:
        CardHoldFactory(target=order)

        assert order_card_hold(order, UserFactory()) is None
        assert order_card_hold(order, bare_staff) is None
        assert order_card_hold(order, staff)["status"] == "authorized"

    def test_no_hold_is_null(self, order, holder) -> None:
        assert order_card_hold(order, holder) is None

    def test_the_interface_is_registered(self) -> None:
        assert graphql_shared_interfaces.get(RelayNode, "CardHoldsInterface") == (
            RelayNode,
            CardHoldsInterface,
        )
        assert CardHold.get_graphql_object_type() is CardHoldObjectType


class TestMutationMixins:
    def test_input_and_payload_fields(self, holder) -> None:
        data = execute(
            """
            mutation($input: HoldableOrderCreateInput!) {
                holdableOrderCreate(input: $input) {
                    ok requiresAction clientSecret intentType
                }
            }
            """,
            holder,
            input={
                "paymentMethodId": "pm_visa",
                "attemptId": str(uuid.uuid4()),
                "paymentIntentId": None,
                "setupIntentId": None,
            },
        )

        assert data["holdableOrderCreate"] == {
            "ok": True,
            "requiresAction": True,
            "clientSecret": "pi_1_secret",
            "intentType": "payment_intent",
        }

    def test_the_payload_hides_the_secret_unless_action_is_required(self) -> None:
        placed = PlacementResult(PlacementStatus.PLACED, client_secret="leak")

        assert card_hold_payload(placed) == {
            "requires_action": False,
            "client_secret": None,
            "intent_type": None,
            "hold_status": "placed",
            "hold_on": None,
        }

    def test_a_scheduled_payload_carries_its_day(self) -> None:
        hold = CardHold(status=CardHold.Status.SCHEDULED, hold_on=datetime.date(2030, 3, 15))

        payload = card_hold_payload(PlacementResult(PlacementStatus.SCHEDULED, hold=hold))

        assert payload["hold_status"] == "scheduled"
        assert payload["hold_on"] == datetime.date(2030, 3, 15)
        assert payload["requires_action"] is False


class TestPermissions:
    def test_view_cardhold_is_the_customers_and_its_grantees(
        self, order, holder, staff, bare_staff
    ) -> None:
        hold = CardHoldFactory(target=order)
        perm = f"{CardHold._meta.app_label}.view_cardhold"

        assert holder.has_perm(perm, hold)
        assert staff.has_perm(perm, hold)
        assert not bare_staff.has_perm(perm, hold)
        assert grant_view_cardhold(UserFactory()).has_perm(perm, hold)
        assert UserFactory(is_superuser=True).has_perm(perm, hold)
        assert not UserFactory().has_perm(perm, hold)
        assert not AnonymousUser().has_perm(perm, hold)
        assert not holder.has_perm(perm, order)  # not a hold

    def test_without_card_holds_the_backend_ignores_the_perm(self, order, holder) -> None:
        from unittest.mock import MagicMock, patch

        from baseapp_payments import permissions
        from baseapp_payments.apps import PackageConfig

        hold = CardHoldFactory(target=order)
        with patch.object(permissions, "card_holds_enabled", return_value=False):
            assert permissions.has_card_hold_perm(holder, "payments.view_cardhold", hold) is None
            assert not holder.has_perm("payments.view_cardhold", hold)

        registry = MagicMock()
        with patch("baseapp_payments.models.card_holds_enabled", return_value=False):
            PackageConfig.register_graphql_shared_interfaces(None, registry)
        registry.register.assert_not_called()


class TestCardHoldListQueryCount:
    QUERY = """
        { holdableOrders { edges { node { id cardHold { status amountCents last4 } } } } }
    """

    HOLD_ON_QUERY = """
        { holdableOrders { edges { node { id cardHold { status holdOn } } } } }
    """

    def count_queries(self, user: Any, query: str | None = None) -> tuple[int, int]:
        ContentType.objects.clear_cache()
        with CaptureQueriesContext(connection) as queries:
            data = execute(query or self.QUERY, user)
        holds = [edge["node"]["cardHold"] for edge in data["holdableOrders"]["edges"]]
        assert all(hold is not None for hold in holds), holds
        self.holds = holds
        return len(queries.captured_queries), len(holds)

    def scheduled_hold(self, holder) -> Any:
        order = HoldableOrderFactory(user=holder, target_date=datetime.date(2030, 3, 20))
        return CardHoldFactory(
            target=order, status=CardHold.Status.SCHEDULED, hold_on=datetime.date(2030, 3, 15)
        )

    def test_hold_on_costs_no_query_per_row(self, holder) -> None:
        """N6: holdOn reads the hold's own stored day, not the target: no query per row."""
        for _ in range(3):
            self.scheduled_hold(holder)
        three, rows = self.count_queries(holder, self.HOLD_ON_QUERY)
        assert rows == 3
        for _ in range(3):
            self.scheduled_hold(holder)

        six, rows = self.count_queries(holder, self.HOLD_ON_QUERY)

        assert rows == 6
        assert six == three == 5, (three, six)
        assert {hold["holdOn"] for hold in self.holds} == {"2030-03-15"}

    def test_a_viewer_with_view_cardhold_costs_one_lookup_per_request(self, holder) -> None:
        """N5 on a list: the model-level grant is looked up once, not once per row."""
        viewer = grant_view_cardhold(UserFactory(is_staff=True))
        for _ in range(3):
            CardHoldFactory(target=HoldableOrderFactory(user=holder))
        viewer = type(viewer).objects.get(pk=viewer.pk)
        three, rows = self.count_queries(viewer)
        for _ in range(3):
            CardHoldFactory(target=HoldableOrderFactory(user=holder))
        viewer = type(viewer).objects.get(pk=viewer.pk)

        six, rows = self.count_queries(viewer)

        assert rows == 6
        assert six == three

    def test_a_viewer_without_it_sees_no_ones_holds_on_a_list(self, holder, bare_staff) -> None:
        CardHoldFactory(target=HoldableOrderFactory(user=holder))

        data = execute(self.QUERY, bare_staff)

        assert [edge["node"]["cardHold"] for edge in data["holdableOrders"]["edges"]] == [None]

    def test_doubling_the_targets_doesnt_change_the_query_count(self, holder) -> None:
        for _ in range(3):
            CardHoldFactory(target=HoldableOrderFactory(user=holder))
        three, rows = self.count_queries(holder)
        assert rows == 3
        for _ in range(3):
            CardHoldFactory(target=HoldableOrderFactory(user=holder))

        six, rows = self.count_queries(holder)

        assert rows == 6
        assert six == three == 5, (
            f"cardHold on a list issued {three} queries for 3 rows and {six} for 6. "
            "Likely causes (in priority order):\n"
            "  - CardHoldsInterface.card_hold lost its optimizer_hook (document__card_hold)\n"
            "  - resolve_card_hold stopped reading the prefetched self.document\n"
            "  - the target model lost DocumentIdMixin's `document` GenericRelation"
        )

    def test_without_the_prefetch_the_resolver_still_answers(self, order, holder) -> None:
        CardHoldFactory(target=order)

        assert order_card_hold(order, holder)["status"] == "authorized"


class TestImportsWithCardHoldsDisabled:
    @pytest.mark.parametrize("module", ["object_types", "interfaces", "mixins"])
    def test_the_graphql_modules_import_without_a_card_hold_model(self, settings, module) -> None:
        settings.BASEAPP_PAYMENTS_CARDHOLD_MODEL = "baseapp_payments.CardHold"  # the default
        path = Path(object_types_module.__file__).with_name(f"{module}.py")
        spec = importlib.util.spec_from_file_location(
            f"baseapp_payments.graphql._disabled_{module}", path
        )
        loaded = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(loaded)

        assert not hasattr(loaded, "CardHoldObjectType")
        if module == "object_types":
            assert hasattr(loaded, "BaseCardHoldObjectType")


class TestCardHoldPrefetchEdges:
    def test_a_target_without_a_hold_or_document_reads_null_on_a_list(self, holder) -> None:
        held = HoldableOrderFactory(user=holder)
        CardHoldFactory(target=held)
        bare = HoldableOrderFactory(user=holder)
        DocumentId.objects.filter(object_id=bare.pk).delete()  # no document row at all
        HoldableOrderFactory(user=holder)  # a document, but no hold

        data = execute(TestCardHoldListQueryCount.QUERY, holder)

        holds = [edge["node"]["cardHold"] for edge in data["holdableOrders"]["edges"]]
        assert sorted(hold is not None for hold in holds) == [False, False, True]

    def test_the_hook_ignores_unoptimized_and_repeated_compiles(self) -> None:
        from types import SimpleNamespace

        from baseapp_payments.graphql.interfaces import (
            CARD_HOLD_PREFETCH_PATH,
            _card_hold_optimizer_hook,
        )

        _card_hold_optimizer_hook(SimpleNamespace(optimizer=None))
        already = SimpleNamespace(
            model=HoldableOrder, prefetch_related={CARD_HOLD_PREFETCH_PATH: 1}
        )
        _card_hold_optimizer_hook(SimpleNamespace(optimizer=already, info=None))

        assert already.prefetch_related == {CARD_HOLD_PREFETCH_PATH: 1}

    def test_a_document_prefetched_without_its_hold_falls_back_to_a_query(
        self, order, holder
    ) -> None:
        from baseapp_payments.models import NOT_PREFETCHED, prefetched_card_hold

        CardHoldFactory(target=order)
        prefetched = HoldableOrder.objects.prefetch_related("document").get(pk=order.pk)

        assert prefetched_card_hold(prefetched) is NOT_PREFETCHED


class TestAnInactiveOwner:
    def test_an_inactive_customer_no_longer_sees_their_hold(self, order) -> None:
        """#11: the owner rule granted by customer_id alone."""
        from baseapp_payments.permissions import (
            card_hold_perm,
            owns_or_oversees_card_hold,
        )

        hold = CardHoldFactory(target=order)
        customer = type(order.user).objects.get(pk=order.user.pk)
        assert owns_or_oversees_card_hold(customer, hold) is True
        assert customer.has_perm(card_hold_perm("view_cardhold"), hold) is True

        customer.is_active = False
        customer.save()
        customer = type(customer).objects.get(pk=customer.pk)

        assert owns_or_oversees_card_hold(customer, hold) is False
        assert customer.has_perm(card_hold_perm("view_cardhold"), hold) is False
