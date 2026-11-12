"""Card hold signals, and the receiver that releases a deleted target's holds."""

from typing import Any

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import Signal

# Sent once the hold is linked to its target and authorized, after the commit.
# Arguments: ``hold`` (the CardHold) and ``target``.
card_hold_authorized = Signal()
# Sent when a hold becomes ``released``, after the commit. Argument: ``hold_id``.
card_hold_released = Signal()
# Sent when a deferred hold fails to be placed (final), after the commit. Arguments:
# ``hold`` (the CardHold, with ``failure_code``) and ``target``.
card_hold_failed = Signal()
# Sent when a hold's ``payment_status`` changes (unpaid, paid, partially_paid), once per
# change, after the commit. Arguments: ``hold``, ``target``, ``previous`` and
# ``payment_status``. Mirror it onto your own record here.
payment_status_changed = Signal()
# Sent when the charge of the difference above a captured hold is refused, once per
# refusal, after the commit: the held amount stays taken and the rest is still due.
# Arguments: ``hold``, ``target``, ``amount_due_cents`` and ``error_code`` (Stripe's
# decline code, or its error code). Notify people and collect the rest from here.
difference_charge_failed = Signal()


def send_on_commit(signal: Signal, **kwargs: Any) -> None:
    """Send ``signal`` from the card hold model once the current transaction commits."""
    from .models import get_card_hold_model

    sender = get_card_hold_model()
    transaction.on_commit(lambda: signal.send_robust(sender=sender, **kwargs), robust=True)


def release_holds_on_target_delete(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Release the open holds of a target being deleted.

    The hold ids are read here, before the cascade nulls the hold's link, and each is
    released once the delete commits.
    """
    from .holds import open_hold_ids_for, release_on_commit

    # Scheduled holds too: released with no Stripe call, so the card is no longer in use.
    for hold_id in open_hold_ids_for(instance):
        release_on_commit(hold_id)


def connect_target_receivers() -> None:
    """Connect :func:`release_holds_on_target_delete` to every registered target model,
    and to its proxies: Django sends ``pre_delete`` with the class of the instance being
    deleted, so a proxy's delete would otherwise skip the receiver."""
    from django.apps import apps

    from .hold_targets import get_targets

    targets = get_targets()
    for model in apps.get_models():
        if model._meta.concrete_model not in targets:
            continue
        pre_delete.connect(
            release_holds_on_target_delete,
            sender=model,
            dispatch_uid=f"baseapp_payments_card_holds_release_{model._meta.label_lower}",
        )
