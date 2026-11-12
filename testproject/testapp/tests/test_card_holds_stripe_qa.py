"""The Stripe test-mode QA command: it only ever runs against a test key, never prints
it, and reports every step in a pass/fail table. Stripe itself is never called here."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from testproject.testapp.management.commands import card_holds_stripe_qa
from testproject.testapp.management.commands.card_holds_stripe_qa import (
    Command,
    QAFailure,
    ensure_test_key,
    expect,
)

LIVE_KEY = "sk_live_must_never_be_printed"
TEST_KEY = "sk_test_must_never_be_printed"


@pytest.mark.parametrize("key", [LIVE_KEY, "rk_live_x", "pk_test_x", "", None])
def test_anything_but_a_test_key_is_refused(settings, key) -> None:
    settings.STRIPE_SECRET_KEY = key
    out, err = StringIO(), StringIO()

    with patch.object(card_holds_stripe_qa, "get_stripe") as get_stripe:
        with pytest.raises(CommandError) as raised:
            call_command("card_holds_stripe_qa", stdout=out, stderr=err)

    get_stripe.assert_not_called()
    assert "test-mode key" in str(raised.value)
    for text in (str(raised.value), out.getvalue(), err.getvalue()):
        assert LIVE_KEY not in text


@pytest.mark.parametrize("key", [TEST_KEY, "rk_test_restricted"])
def test_a_test_key_passes_the_guard(settings, key) -> None:
    settings.STRIPE_SECRET_KEY = key

    ensure_test_key()


def test_every_step_is_a_row_and_a_failure_fails_the_command(settings) -> None:
    settings.STRIPE_SECRET_KEY = TEST_KEY
    out = StringIO()

    def passes() -> str:
        return "fine"

    def fails() -> str:
        expect(False, "the difference wasn't charged")
        return ""  # pragma: no cover

    steps = [("a step that passes", passes), ("a step that fails", fails)]
    with (
        patch.object(card_holds_stripe_qa, "get_stripe"),
        patch.object(Command, "steps", return_value=steps),
    ):
        with pytest.raises(CommandError, match="Stripe QA failed"):
            call_command("card_holds_stripe_qa", stdout=out)

    table = out.getvalue()
    assert "a step that passes" in table and "PASS" in table and "fine" in table
    assert "a step that fails" in table and "FAIL" in table
    assert "QAFailure: the difference wasn't charged" in table
    assert TEST_KEY not in table


def test_all_steps_passing_succeeds(settings) -> None:
    settings.STRIPE_SECRET_KEY = TEST_KEY
    out = StringIO()

    with (
        patch.object(card_holds_stripe_qa, "get_stripe"),
        patch.object(Command, "steps", return_value=[("only", lambda: "ok")]),
    ):
        call_command("card_holds_stripe_qa", stdout=out)

    assert "PASS" in out.getvalue()


def test_the_command_lists_the_story_flows() -> None:
    names = [name for name, _step in Command().steps()]

    assert names == [
        "save a card",
        "subscription renews (basil period fields)",
        "hold captured within it",
        "above the hold: paid, two payments, one invoice, fees",
        "difference declined: partially_paid + signal",
        "marked paid outside: paid",
        "expired hold: one full charge",
    ]


def test_capture_paths_that_must_not_charge_say_so() -> None:
    with pytest.raises(QAFailure):
        Command.fail_if_charged(idempotency_key="k")
