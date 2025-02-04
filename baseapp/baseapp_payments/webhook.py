import logging

import swapper
from django.db import transaction
from djstripe import webhooks
from djstripe.models import Subscription

from .emails import send_subscription_trial_will_end_email


@webhooks.handler("invoice.paid")
def subscription_plan_changed_webhook(event, **kwargs):
    subscription = Subscription.objects.active().filter(customer=event.customer).first()
    if not subscription:
        return
    current_plan = subscription.customer.subscriber.get_subscription_plan()
    if not current_plan:
        return
    current_price = current_plan.price
    invoice_price = subscription.plan

    if current_price and invoice_price and current_price.id != invoice_price.id:
        logging.info(
            f"Different plans found: {current_price.id} and {invoice_price.id}, local plan will be updated."
        )
        Plan = swapper.load_model("baseapp_payments", "Plan")
        plan = Plan.objects.get(price=invoice_price)
        transaction.on_commit(
            lambda: event.customer.subscriber.subscription_plan_changed_webhook(
                price=invoice_price, plan=plan, event=event
            )
        )


def on_subscription_deleted_webhook(event):
    if event.customer and event.customer.subscriber:
        event.customer.subscriber.subscription_deleted_webhook(event=event)


@webhooks.handler("customer.subscription.deleted")
def subscription_deleted_webhook(event, **kwargs):
    transaction.on_commit(lambda: on_subscription_deleted_webhook(event))


def on_invoice_payment_failed_webhook(event):
    if event.customer and event.customer.subscriber:
        event.customer.subscriber.invoice_payment_failed_webhook(event=event)


@webhooks.handler("invoice.payment_failed")
def invoice_payment_failed_webhook(event, **kwargs):
    transaction.on_commit(lambda: on_invoice_payment_failed_webhook(event))


def on_subscription_trial_will_end_webhook(event):
    subscription = (
        Subscription.objects.all().filter(customer=event.customer, status="trialing").first()
    )
    if subscription and event.owner.email:
        Plan = swapper.load_model("baseapp_payments", "Plan")
        plan = Plan.objects.get(price=subscription.plan)

        send_subscription_trial_will_end_email(event.owner.email, plan.name)


@webhooks.handler("customer.subscription.trial_will_end")
def subscription_trial_will_end_webhook(event, **kwargs):
    transaction.on_commit(lambda: on_subscription_trial_will_end_webhook(event))
