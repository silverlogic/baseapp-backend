"""Pure helpers of card holds: pricing, settings, and reading Stripe objects."""

import ast
import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
import stripe
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from stripe._stripe_response import StripeResponse

from baseapp_payments import hold_targets, holds
from baseapp_payments.hold_targets import (
    BaseHoldTarget,
    HoldAmount,
    HoldAmountMode,
    HoldTarget,
    get_targets,
    target_for_model,
)
from baseapp_payments.holds import hold_amount_cents, idempotency_key
from baseapp_payments.utils import (
    capture_before,
    card_of,
    is_idempotent_replay,
    normalize_funding,
)
from testproject.testapp.card_holds import HoldableOrderHoldTarget

PACKAGE = Path(__file__).resolve().parents[2]
HERE = "baseapp_payments.tests.unit.test_card_hold_helpers"


class UndeclaredTarget(BaseHoldTarget):
    """Says neither whether it uses holds nor what they cover."""


class HoldsWithoutModeTarget(BaseHoldTarget):
    uses_holds = True


class HoldsWithBadModeTarget(BaseHoldTarget):
    uses_holds = True
    hold_amount_mode = "value_plus_some"


class ValueTarget(BaseHoldTarget):
    uses_holds = True
    hold_amount_mode = "value"

    def hold_amount(self, target, card=None) -> HoldAmount:
        return HoldAmount(estimated_cents=10_000, buffer_percent=Decimal("25"))


class BufferTarget(ValueTarget):
    hold_amount_mode = HoldAmountMode.VALUE_PLUS_BUFFER


class DirectChargeTarget(BaseHoldTarget):
    uses_holds = False

    def hold_amount(self, target, card=None) -> HoldAmount:
        return HoldAmount(estimated_cents=10_000, buffer_percent=Decimal("25"))


@pytest.mark.parametrize(
    "estimated, buffer, held",
    [
        (10_000, Decimal("10"), 11_000),
        (10_001, Decimal("10"), 11_002),  # 11001.1 rounds up
        (999, Decimal("0"), 999),
        (1, Decimal("12.5"), 2),
        (0, Decimal("10"), 0),
    ],
)
def test_the_hold_amount_rounds_up_to_the_cent(estimated, buffer, held) -> None:
    assert hold_amount_cents(estimated, buffer) == held


def test_the_idempotency_key_carries_the_prefix_user_and_attempt(settings) -> None:
    settings.BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = "acme"

    class User:
        pk = 7

    assert idempotency_key(User(), "a-1") == "acme-hold-7-a-1"
    settings.BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = ""
    assert holds.key_prefix() == "baseapp"


class TestConstance:
    def test_defaults(self) -> None:
        assert hold_targets.default_buffer_percent() == Decimal("10")
        assert hold_targets.default_window_days() == 4
        assert hold_targets.deferral_enabled() is False

    @pytest.mark.parametrize("value, days", [(0, 1), (3, 3), (4, 4), (5, 4), (9, 4)])
    def test_the_window_is_clamped_to_one_to_four_days(self, value, days) -> None:
        """M3: a Visa off-session hold lasts 4 days 18 hours; a 5-day window outlives it."""
        with patch.object(hold_targets, "_constance", return_value=value):
            assert hold_targets.default_window_days() == days

    def test_a_negative_buffer_is_zero(self) -> None:
        with patch.object(hold_targets, "_constance", return_value=-5):
            assert hold_targets.default_buffer_percent() == Decimal("0")

    def test_keys_missing_from_constance_fall_back(self) -> None:
        assert hold_targets._constance("CARD_HOLDS_NOT_A_KEY", 42) == 42

    def test_the_plugin_contributes_the_keys(self) -> None:
        from baseapp_core.plugins import plugin_registry

        keys = dict(plugin_registry.get_all_constance_config())
        assert keys["CARD_HOLDS_BUFFER_PERCENT"][0] == 10
        assert keys["CARD_HOLDS_WINDOW_DAYS"][0] == 4
        assert "1-4" in keys["CARD_HOLDS_WINDOW_DAYS"][1]
        assert keys["CARD_HOLDS_DEFERRAL_ENABLED"][0] is False


class TestReadingStripe:
    def test_card_of_an_expanded_payment_method(self) -> None:
        card = card_of(
            {
                "id": "pm_1",
                "card": {
                    "brand": "amex",
                    "last4": "0005",
                    "exp_month": 1,
                    "exp_year": 2031,
                    "funding": "charge",
                },
            }
        )
        assert (card.payment_method_id, card.brand, card.funding, card.fingerprint) == (
            "pm_1",
            "amex",
            "unknown",
            "",
        )

    def test_card_of_a_bare_id(self) -> None:
        assert card_of("pm_2").payment_method_id == "pm_2"
        assert card_of(None).payment_method_id == ""

    def test_funding_types(self) -> None:
        assert [normalize_funding(f) for f in ("credit", "debit", "prepaid", None)] == [
            "credit",
            "debit",
            "prepaid",
            "unknown",
        ]

    def test_replays_are_read_from_the_header(self) -> None:
        replayed = stripe.PaymentIntent.construct_from(
            {"id": "pi"},
            "sk",
            last_response=StripeResponse("{}", 200, {"idempotent-replayed": "true"}),
        )
        fresh = stripe.PaymentIntent.construct_from({"id": "pi"}, "sk")
        assert is_idempotent_replay(replayed)
        assert not is_idempotent_replay(fresh)

    def test_capture_before(self) -> None:
        intent = {
            "latest_charge": {"payment_method_details": {"card": {"capture_before": 1_900_000_000}}}
        }
        assert capture_before(intent) == datetime.datetime(
            2030, 3, 17, 17, 46, 40, tzinfo=datetime.timezone.utc
        )
        assert capture_before({"latest_charge": "ch_1"}) is None


class TestTargets:
    def test_the_registry_builds_adapters_once(self) -> None:
        targets = get_targets()
        (model,) = targets
        assert isinstance(targets[model], HoldableOrderHoldTarget)
        assert isinstance(targets[model], HoldTarget)
        assert get_targets() is targets

    def test_an_unregistered_model_is_a_configuration_error(self) -> None:
        from django.contrib.auth import get_user_model

        with pytest.raises(ImproperlyConfigured):
            target_for_model(get_user_model())

    def test_an_unknown_model_is_a_configuration_error(self, settings) -> None:
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {"nope.Missing": "x.Y"}
        with pytest.raises(ImproperlyConfigured):
            get_targets()

    def test_the_adapter_gets_its_model_when_it_names_none(self, settings) -> None:
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
            "testapp.HoldableOrder": f"{HERE}.DirectChargeTarget"
        }
        (adapter,) = get_targets().values()
        assert adapter.model._meta.label == "testapp.HoldableOrder"

    @pytest.mark.parametrize(
        "adapter, message",
        [
            ("UndeclaredTarget", "must declare uses_holds"),
            ("HoldsWithoutModeTarget", "must declare hold_amount_mode"),
            ("HoldsWithBadModeTarget", "not 'value_plus_some'"),
        ],
    )
    def test_a_missing_declaration_fails_loudly_at_registration(
        self, settings, adapter, message
    ) -> None:
        """Product change 2: no silent default for using holds or what they cover."""
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {"testapp.HoldableOrder": f"{HERE}.{adapter}"}
        with pytest.raises(ImproperlyConfigured, match=message):
            get_targets()

    def test_a_string_mode_is_normalized(self, settings) -> None:
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
            "testapp.HoldableOrder": f"{HERE}.ValueTarget"
        }
        (adapter,) = get_targets().values()
        assert adapter.hold_amount_mode is HoldAmountMode.VALUE

    def test_an_adapter_without_holds_needs_no_mode(self, settings) -> None:
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
            "testapp.HoldableOrder": f"{HERE}.DirectChargeTarget"
        }
        (adapter,) = get_targets().values()
        assert adapter.uses_holds is False

    def test_a_proxy_target_is_rejected(self, settings) -> None:
        """m3: a proxy's content type is its concrete model's, so a hold on it would back
        an "unregistered" target."""
        from ..helpers import holdable_order_proxy

        holdable_order_proxy()
        settings.BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
            "testapp.HoldableOrderProxy": "testproject.testapp.card_holds.HoldableOrderHoldTarget"
        }
        with pytest.raises(ImproperlyConfigured, match="proxy model.*testapp.HoldableOrder"):
            get_targets()

    @pytest.mark.django_db
    def test_the_base_defaults(self, django_user_model) -> None:
        adapter = BaseHoldTarget()
        adapter.model = django_user_model
        from ..helpers import grant_card_hold_perm

        django_user_model.objects.create(email="staff@example.com", is_staff=True)
        granted = grant_card_hold_perm(
            django_user_model.objects.create(email="granted@example.com")
        )
        group = Group.objects.create(name="hold deciders")
        group.permissions.add(*granted.user_permissions.all())
        django_user_model.objects.create(email="grouped@example.com").groups.add(group)
        django_user_model.objects.create(email="root@example.com", is_superuser=True)
        inactive = grant_card_hold_perm(
            django_user_model.objects.create(email="gone@example.com", is_active=False)
        )
        assert inactive.is_active is False
        for hook in ("owner", "hold_amount", "target_date", "filter_cancelled", "cancel"):
            with pytest.raises(NotImplementedError):
                getattr(adapter, hook)(*([None, None] if hook == "cancel" else [None]))
        assert adapter.charge_may_be_in_flight(None) is False
        assert adapter.filter_holdable(django_user_model.objects.all()).count() == 5
        assert not adapter.filter_card_released(django_user_model.objects.all()).exists()
        # Staff status alone isn't enough: change_cardhold (directly or by group) or superuser.
        assert sorted(user.email for user in adapter.staff_recipients(None)) == [
            "granted@example.com",
            "grouped@example.com",
            "root@example.com",
        ]
        assert adapter.window_days() == 4
        assert adapter.buffer_percent() == Decimal("10")


def _module_level_imports(nodes: list, guarded: bool = False) -> list[tuple[str, bool]]:
    """``(module, guarded)`` of every import that runs at import time (not in a function or
    class body); ``guarded``: inside a ``try`` that handles ``ImportError``."""
    found = []
    for node in nodes:
        if isinstance(node, ast.Import):
            found += [(alias.name, guarded) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", guarded))
        elif isinstance(node, ast.Try):
            handles = any(
                isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
                for handler in node.handlers
            )
            found += _module_level_imports(node.body, guarded or handles)
        elif isinstance(node, ast.If) and not (
            isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
        ):
            found += _module_level_imports(node.body + node.orelse, guarded)
    return found


@pytest.mark.parametrize(
    "module",
    [
        "admin.py",
        "apps.py",
        "hold_targets.py",
        "holds.py",
        "models.py",
        "permissions.py",
        "plugin.py",
        "signals.py",
        "tasks.py",
        "utils.py",
    ],
)
def test_rest_only_modules_import_no_graphql_at_import_time(module) -> None:
    """Card holds add no import-time GraphQL dependency to the modules they touch: GraphQL
    is imported lazily, or guarded by ``except ImportError``. (``serializers.py`` and
    ``views.py`` already imported ``baseapp_core.graphql`` before card holds.)"""
    tree = ast.parse((PACKAGE / module).read_text())
    graphql = [
        (name, guarded)
        for name, guarded in _module_level_imports(tree.body)
        if "graphql" in name or "graphene" in name
    ]
    assert all(guarded for _name, guarded in graphql), graphql


class TestStripeConfiguration:
    def test_get_stripe_and_stripe_service_share_one_setup_read_at_call_time(
        self, settings
    ) -> None:
        from baseapp_payments.utils import StripeService, get_stripe

        settings.STRIPE_SECRET_KEY = "sk_test_now"
        settings.STRIPE_API_VERSION = "2030-01-01.test"

        assert get_stripe().api_key == "sk_test_now"
        assert stripe.api_version == "2030-01-01.test"

        settings.STRIPE_SECRET_KEY = "sk_test_later"
        StripeService()
        assert stripe.api_key == "sk_test_later"

    def test_the_key_prefix_has_one_default(self, settings) -> None:
        from baseapp_payments.plugin import DEFAULT_CARD_HOLD_KEY_PREFIX

        settings.BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = None
        assert holds.key_prefix() == DEFAULT_CARD_HOLD_KEY_PREFIX


class TestCardHoldPermission:
    def test_an_unrelated_perm_never_reaches_the_card_hold_model(self) -> None:
        from baseapp_payments import permissions

        with patch.object(permissions, "get_card_hold_model", side_effect=AssertionError):
            assert permissions.has_card_hold_perm(object(), "payments.view_customer", None) is None

    def test_the_perm_string_is_built_once(self) -> None:
        from baseapp_payments import permissions

        permissions._card_hold_perm.cache_clear()
        permissions.card_hold_perm("view_cardhold")
        permissions.card_hold_perm("view_cardhold")

        assert permissions._card_hold_perm.cache_info().hits >= 1


class TestDeferredHelpers:
    def test_the_scheduled_key_changes_with_each_attempt_and_authorization(self, settings) -> None:
        from types import SimpleNamespace

        settings.BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = "acme"
        hold = SimpleNamespace(
            pk=7, attempt_id="a1", previous_payment_intent_ids=[], placement_generation=0
        )

        assert holds.scheduled_idempotency_key(hold) == "acme-hold-scheduled-7-a1-0"
        hold.previous_payment_intent_ids = ["pi_1"]
        assert holds.scheduled_idempotency_key(hold) == "acme-hold-scheduled-7-a1-1"
        hold.attempt_id = "a2"
        assert holds.scheduled_idempotency_key(hold).endswith("-a2-1")
        # A placement reconciled with nothing found in Stripe gets a new key.
        hold.placement_generation = 1
        assert holds.scheduled_idempotency_key(hold).endswith("-a2-1-1")

    def test_the_setup_key_carries_the_user_and_attempt(self, settings) -> None:
        from types import SimpleNamespace

        settings.BASEAPP_PAYMENTS_CARD_HOLD_KEY_PREFIX = "acme"

        assert holds.setup_idempotency_key(SimpleNamespace(pk=3), "a1") == "acme-setup-3-a1"

    @pytest.mark.parametrize("window, days", [(0, 1), (3, 3), (5, 4), (9, 4)])
    def test_an_adapter_window_is_clamped(self, window, days) -> None:
        adapter = HoldableOrderHoldTarget()
        with patch.object(HoldableOrderHoldTarget, "window_days", return_value=window):
            assert hold_targets.window_days_of(adapter) == days

    @pytest.mark.parametrize(
        "error, code",
        [
            (stripe.APIConnectionError("down"), None),
            (stripe.APIError("5xx", http_status=500), None),
            (stripe.RateLimitError("429", http_status=429), None),
            (stripe.APIError("409", http_status=409), None),
            (stripe.IdempotencyError("reused"), "IdempotencyError"),
            (stripe.CardError("no", None, "card_declined"), "card_declined"),
            (
                stripe.CardError(
                    "no",
                    None,
                    "card_declined",
                    json_body={"error": {"decline_code": "insufficient_funds"}},
                ),
                "insufficient_funds",
            ),
            (stripe.CardError("no", None, None), "card_declined"),
            (stripe.InvalidRequestError("gone", None, code="resource_missing"), "resource_missing"),
            # M2: a bad or revoked key, or any other error that isn't about the request,
            # is no usable answer, never a failed hold.
            (stripe.AuthenticationError("bad key", http_status=401), None),
            (stripe.PermissionError("revoked", http_status=403), None),
            (stripe.StripeError("something else"), None),
        ],
    )
    def test_which_errors_are_final(self, error, code) -> None:
        assert holds._placement_failure(None, error) == code

    @pytest.mark.parametrize(
        "status, code",
        [
            ("requires_capture", None),
            ("processing", None),
            ("requires_action", "authentication_required"),
            ("requires_payment_method", "requires_payment_method"),
            (None, "unknown"),
        ],
    )
    def test_which_statuses_are_final(self, status, code) -> None:
        assert holds._placement_failure({"status": status}, None) == code

    def test_the_base_adapter_emails_staff_recipients(self) -> None:
        sent = []
        adapter = BaseHoldTarget()
        with (
            patch.object(BaseHoldTarget, "staff_recipients", return_value=["staff"]),
            patch(
                "baseapp_payments.emails.send_hold_failed_email",
                side_effect=lambda *args: sent.append(args),
            ),
        ):
            adapter.notify_hold_failed("target", "hold")

        assert sent == [("hold", "target", ["staff"])]

    def test_a_customer_is_named_by_name_and_email_or_whatever_there_is(self) -> None:
        from types import SimpleNamespace

        from baseapp_payments.emails import _customer_name

        def user(name: str, email: str) -> SimpleNamespace:
            return SimpleNamespace(pk=5, email=email, get_full_name=lambda: name)

        assert _customer_name(user("Ana", "a@x.io")) == "Ana <a@x.io>"
        assert _customer_name(user("", "a@x.io")) == "a@x.io"
        assert _customer_name(user("", "")) == "5"


class TestHoldAmountMode:
    """Product change 2: what a hold covers is the adapter's declaration."""

    def test_value_holds_the_value_alone_whatever_buffer_is_returned(self) -> None:
        assert holds.price(ValueTarget(), None, None) == (10_000, Decimal(0), 10_000)

    def test_value_plus_buffer_uses_the_returned_buffer(self) -> None:
        assert holds.price(BufferTarget(), None, None) == (10_000, Decimal(25), 12_500)

    def test_value_plus_buffer_falls_back_to_the_adapter_then_constance(self) -> None:
        adapter = BufferTarget()
        with patch.object(
            BufferTarget, "hold_amount", return_value=HoldAmount(estimated_cents=10_000)
        ):
            assert holds.price(adapter, None, None) == (10_000, Decimal(10), 11_000)
            with patch.object(hold_targets, "_constance", return_value=20):
                assert holds.price(adapter, None, None)[2] == 12_000
            with patch.object(BufferTarget, "buffer_percent", return_value=Decimal(5)):
                assert holds.price(adapter, None, None)[2] == 10_500

    def test_an_adapter_without_holds_holds_nothing(self) -> None:
        assert holds.price(DirectChargeTarget(), None, None) == (10_000, Decimal(0), 0)


class TestChargedLater:
    """Product change 3: only a target charged after today takes a hold."""

    @pytest.mark.parametrize(
        "offset, later", [(None, False), (-1, False), (0, False), (1, True), (30, True)]
    )
    def test_only_a_date_after_today(self, offset, later) -> None:
        from django.utils import timezone

        when = None if offset is None else timezone.localdate() + datetime.timedelta(days=offset)
        with patch.object(DirectChargeTarget, "target_date", return_value=when):
            assert holds.charged_later(DirectChargeTarget(), None) is later
