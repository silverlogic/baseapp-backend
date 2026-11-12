"""End-to-end QA of ``baseapp_payments`` against Stripe **test mode**.

    docker compose exec -T web uv run --python 3.12 python manage.py card_holds_stripe_qa

Runs every payments flow the basil upgrade and the above-the-hold capture touch, against
the real Stripe API with Stripe's test cards, and prints a pass/fail table. It refuses to
run unless ``STRIPE_SECRET_KEY`` is a test key (``sk_test_`` / ``rk_test_``), and never
prints it. It creates Stripe test objects (customers, a product, a test clock) and test
project rows; nothing is cleaned up, so run it against a scratch database.
"""

import datetime
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from celery import current_app
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from baseapp_payments.utils import get_stripe

logger = logging.getLogger(__name__)

TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
# Attaches to a customer, then every charge on it fails ("attach succeeds, charge fails").
DECLINING_CARD = "pm_card_chargeCustomerFail"
CLOCK_TIMEOUT_SECONDS = 120


def ensure_test_key() -> None:
    """Refuse anything but a Stripe test-mode key. The key itself is never printed."""
    key = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    if not key.startswith(TEST_KEY_PREFIXES):
        raise CommandError(
            "STRIPE_SECRET_KEY must be a Stripe test-mode key (sk_test_... or rk_test_...);"
            " refusing to run."
        )


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


class QAFailure(AssertionError):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise QAFailure(message)


class Command(BaseCommand):
    help = "Run the Stripe test-mode QA of card holds, subscriptions and the basil upgrade."

    def handle(self, *args: Any, **options: Any) -> None:
        ensure_test_key()
        self.stripe = get_stripe()
        self.run_id = uuid.uuid4().hex[:8]
        # Releases and reconciles queue Celery tasks: run them in this process.
        eager = {"task_always_eager": True, "task_eager_propagates": True}
        saved = {key: current_app.conf.get(key) for key in eager}
        current_app.conf.update(eager)
        try:
            results = [self.run_step(name, step) for name, step in self.steps()]
        finally:
            current_app.conf.update(saved)
        self.print_table(results)
        if not all(result.passed for result in results):
            raise CommandError("Stripe QA failed")

    def steps(self) -> list[tuple[str, Callable[[], str]]]:
        return [
            ("save a card", self.save_card),
            ("subscription renews (basil period fields)", self.subscription_renews),
            ("hold captured within it", self.capture_within_hold),
            ("above the hold: paid, two payments, one invoice, fees", self.capture_above_hold),
            ("difference declined: partially_paid + signal", self.difference_declined),
            ("marked paid outside: paid", self.mark_paid),
            ("expired hold: one full charge", self.expired_hold_full_charge),
        ]

    def run_step(self, name: str, step: Callable[[], str]) -> Check:
        try:
            return Check(name, True, step() or "")
        except Exception as error:
            # Every failure is a row in the table; the traceback goes to the log.
            logger.exception("Stripe QA step %r failed", name)
            return Check(name, False, f"{type(error).__name__}: {error}")

    def print_table(self, results: list[Check]) -> None:
        width = max(len(result.name) for result in results)
        self.stdout.write(f"{'check'.ljust(width)}  result  detail")
        for result in results:
            verdict = "PASS" if result.passed else "FAIL"
            style = self.style.SUCCESS if result.passed else self.style.ERROR
            self.stdout.write(
                f"{result.name.ljust(width)}  {style(verdict.ljust(6))}  {result.detail}"
            )

    # --- Fixtures --------------------------------------------------------------------

    def customer(self, **params: Any) -> Any:
        return self.stripe.Customer.create(
            email=f"card-holds-qa-{self.run_id}@example.com",
            metadata={"qa_run": self.run_id},
            **params,
        )

    def attach(self, customer_id: str, test_card: str) -> str:
        """Save ``test_card`` for off-session use, as the frontend's SetupIntent does."""
        setup = self.stripe.SetupIntent.create(
            customer=customer_id,
            payment_method=test_card,
            payment_method_types=["card"],
            usage="off_session",
            confirm=True,
        )
        expect(setup.status == "succeeded", f"SetupIntent ended {setup.status}")
        return setup.payment_method

    def holder(self) -> tuple[Any, str, str]:
        """A local user with a Stripe customer and a saved Visa, once per run."""
        if not hasattr(self, "_holder"):
            user = get_user_model().objects.create(email=f"card-holds-qa-{self.run_id}@example.com")
            customer = self.customer()
            self._holder = (user, customer.id, self.attach(customer.id, "pm_card_visa"))
        return self._holder

    def placed_hold(self, amount_cents: int = 10_000) -> Any:
        """A $100.00 order two days out, held at checkout for $110.00 (10% buffer)."""
        from baseapp_payments.holds import PlacementStatus, authorize_on_session
        from testproject.testapp.models import HoldableOrder

        user, customer_id, payment_method_id = self.holder()
        order = HoldableOrder(
            user=user,
            amount_cents=amount_cents,
            target_date=timezone.localdate() + datetime.timedelta(days=2),
        )

        def link(hold: Any) -> Any:
            order.save()
            return order

        result = authorize_on_session(
            user=user,
            attempt_id=uuid.uuid4(),
            stripe_customer_id=customer_id,
            payment_method_id=payment_method_id,
            target=order,
            link=link,
        )
        expect(result.status == PlacementStatus.PLACED, f"placing answered {result.status}")
        return result.hold

    def charge(self, amount_cents: int, payment_method_id: str, customer_id: str) -> Callable:
        """The project's ``charge`` for ``capture()``: the full amount, off-session."""

        def charge(*, idempotency_key: str) -> Any:
            return self.stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=customer_id,
                payment_method=payment_method_id,
                payment_method_types=["card"],
                confirm=True,
                off_session=True,
                expand=["latest_charge.balance_transaction"],
                idempotency_key=idempotency_key,
            )

        return charge

    # --- Steps -----------------------------------------------------------------------

    def save_card(self) -> str:
        _user, customer_id, payment_method_id = self.holder()
        cards = self.stripe.PaymentMethod.list(customer=customer_id, type="card")
        expect(
            payment_method_id in [card.id for card in cards.auto_paging_iter()],
            "the saved card isn't on the customer",
        )
        return payment_method_id

    def subscription_renews(self) -> str:
        from baseapp_payments.utils import StripeService, subscription_period

        clock = self.stripe.test_helpers.TestClock.create(
            frozen_time=int(time.time()), name=f"card-holds-qa-{self.run_id}"
        )
        customer = self.customer(test_clock=clock.id)
        payment_method_id = self.attach(customer.id, "pm_card_visa")
        price = self.stripe.Price.create(
            currency="usd",
            unit_amount=1_000,
            recurring={"interval": "month"},
            product_data={"name": f"Card holds QA {self.run_id}"},
        )
        service = StripeService()
        subscription = service.create_incomplete_subscription(
            customer.id, price.id, payment_method_id=payment_method_id
        )
        subscription = self.stripe.Subscription.modify(
            subscription.id, default_payment_method=payment_method_id
        )
        first_end = subscription_period(subscription, "current_period_end")
        expect(first_end is not None, "no current_period_end on the subscription's items")
        self.stripe.test_helpers.TestClock.advance(clock.id, frozen_time=first_end + 24 * 60 * 60)
        deadline = time.monotonic() + CLOCK_TIMEOUT_SECONDS
        while self.stripe.test_helpers.TestClock.retrieve(clock.id).status != "ready":
            expect(time.monotonic() < deadline, "the test clock never finished advancing")
            time.sleep(2)
        renewed = self.stripe.Subscription.retrieve(subscription.id)
        next_end = subscription_period(renewed, "current_period_end")
        expect(next_end and next_end > first_end, f"period end {first_end} -> {next_end}")
        return f"period end {first_end} -> {next_end}"

    def capture_within_hold(self) -> str:
        from baseapp_payments.holds import CaptureStatus, capture, record_fees

        hold = self.placed_hold()
        result = capture(hold.pk, hold.amount_cents - 1, charge=self.fail_if_charged)
        expect(result.status == CaptureStatus.CAPTURED, f"capture answered {result.status}")
        record_fees(hold.pk)
        hold.refresh_from_db()
        expect(hold.payment_status == "paid", f"payment status {hold.payment_status}")
        return f"captured {hold.captured_amount_cents}, fee {hold.capture_fee_cents}"

    def capture_above_hold(self) -> str:
        from baseapp_payments.holds import (
            CaptureStatus,
            attach_payments_to_invoice,
            capture,
            record_fees,
        )

        hold = self.placed_hold()
        total = hold.amount_cents + 1_500
        result = capture(hold.pk, total, charge=self.fail_if_charged)
        expect(result.status == CaptureStatus.PAID, f"capture answered {result.status}")
        record_fees(hold.pk)
        hold.refresh_from_db()
        expect(hold.payment_status == "paid", f"payment status {hold.payment_status}")
        expect(
            hold.capture_fee_cents is not None and hold.difference_fee_cents is not None,
            "a fee is missing",
        )
        invoice = self.invoice(hold.stripe_customer_id, total)
        attached = attach_payments_to_invoice(hold.pk, invoice.id)
        invoice = self.stripe.Invoice.retrieve(invoice.id, expand=["payments"])
        expect(len(attached) == 2, f"{len(attached)} payments attached")
        expect(
            invoice.status == "paid" and invoice.amount_paid == total,
            f"invoice {invoice.status}, paid {invoice.amount_paid} of {total}",
        )
        return (
            f"invoice {invoice.id} paid by {', '.join(attached)};"
            f" fees {hold.capture_fee_cents} + {hold.difference_fee_cents}"
        )

    def invoice(self, customer_id: str, amount_cents: int) -> Any:
        """The project's invoice for the target, finalized and left for the payments."""
        draft = self.stripe.Invoice.create(
            customer=customer_id,
            collection_method="send_invoice",
            days_until_due=1,
            auto_advance=False,
            pending_invoice_items_behavior="exclude",
        )
        self.stripe.InvoiceItem.create(
            customer=customer_id,
            invoice=draft.id,
            amount=amount_cents,
            currency="usd",
            description="Card holds QA order",
        )
        return self.stripe.Invoice.finalize_invoice(draft.id, auto_advance=False)

    def difference_declined(self) -> str:
        from baseapp_payments.holds import CaptureStatus, capture
        from baseapp_payments.signals import difference_charge_failed

        hold = self.placed_hold()
        # Stripe has no test card that authorizes once and declines later, so the hold's
        # card is swapped for one that declines every charge, once the hold is placed.
        _user, customer_id, _visa = self.holder()
        type(hold).objects.filter(pk=hold.pk).update(
            stripe_payment_method_id=self.attach(customer_id, DECLINING_CARD)
        )
        failures: list[dict[str, Any]] = []

        def heard(sender: Any, **kwargs: Any) -> None:
            failures.append(kwargs)

        difference_charge_failed.connect(heard, weak=False)
        try:
            result = capture(hold.pk, hold.amount_cents + 500, charge=self.fail_if_charged)
        finally:
            difference_charge_failed.disconnect(heard)
        hold.refresh_from_db()
        expect(result.status == CaptureStatus.PARTIALLY_PAID, f"capture answered {result.status}")
        expect(hold.payment_status == "partially_paid", f"payment status {hold.payment_status}")
        expect(len(failures) == 1, f"difference_charge_failed sent {len(failures)} times")
        self._partially_paid = hold
        return f"declined: {failures[0]['error_code']}, {failures[0]['amount_due_cents']} due"

    def mark_paid(self) -> str:
        from baseapp_payments.holds import mark_paid_outside

        hold = getattr(self, "_partially_paid", None)
        expect(hold is not None, "no partially paid hold (the step before failed)")
        expect(mark_paid_outside(hold.pk), "mark_paid_outside refused")
        hold.refresh_from_db()
        expect(hold.payment_status == "paid", f"payment status {hold.payment_status}")
        return "paid"

    def expired_hold_full_charge(self) -> str:
        from baseapp_payments.holds import (
            CaptureStatus,
            capture,
            hold_payment_intent_ids,
        )

        hold = self.placed_hold()
        # Expired as far as the module knows: capture() charges afresh, never captures.
        type(hold).objects.filter(pk=hold.pk).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )
        total = hold.amount_cents + 2_000
        result = capture(
            hold.pk,
            total,
            charge=self.charge(total, hold.stripe_payment_method_id, hold.stripe_customer_id),
        )
        hold.refresh_from_db()
        expect(result.status == CaptureStatus.CHARGED, f"capture answered {result.status}")
        payments = hold_payment_intent_ids(hold)
        expect(len(payments) == 1, f"{len(payments)} payments")
        expect(hold.charge_fee_cents is not None, "no fee for the full charge")
        return f"charged {hold.charge_amount_cents} once ({payments[0]})"

    @staticmethod
    def fail_if_charged(**kwargs: Any) -> Any:
        raise QAFailure("capture() ran the project's charge on a path that must not")
