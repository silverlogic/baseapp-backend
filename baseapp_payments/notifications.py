"""In-app notifications to staff about a card hold that needs them.

Sent through the ``notifications`` shared service (``baseapp_notifications``) with the hold as
the notification's target, so the client renders the hold's staff notice and its actions in
the notification. Nothing is sent when that package isn't installed. The customer is never
notified.
"""

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from django.utils import translation
from django.utils.translation import gettext_lazy as _

from baseapp_core.i18n import group_by_language
from baseapp_core.plugins import shared_services

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.db.models import Model

    from .models import AbstractCardHold

CARD_HOLD_FAILED_VERB = "PAYMENTS.CARD_HOLD_FAILED"
CARD_HOLD_PARTIALLY_PAID_VERB = "PAYMENTS.CARD_HOLD_PARTIALLY_PAID"


def _actor(hold: "AbstractCardHold") -> Any:
    """The customer, as their profile when they have one (what notification avatars show)."""
    customer = hold.customer
    return getattr(customer, "profile", None) or customer


def _notify_staff(
    verb: str,
    hold: "AbstractCardHold",
    recipients: Iterable["AbstractBaseUser"],
    describe: Callable[[], str],
) -> None:
    """One in-app notification per recipient, worded in the recipient's language. Email and
    push are left to the caller: the failed-hold email has its own wording."""
    service = shared_services.get("notifications")
    if not service:
        return
    actor = _actor(hold)
    for language, group in group_by_language(list(recipients)).items():
        with translation.override(language):
            text = describe()
        for recipient in group:
            service.send_notification(
                sender=actor,
                recipient=recipient,
                verb=verb,
                target=hold,
                description=text,
                level="warning",
                add_to_history=True,
                send_email=False,
                send_push=False,
            )


def notify_hold_failed_in_app(
    hold: "AbstractCardHold", target: "Model", recipients: Iterable["AbstractBaseUser"]
) -> None:
    """Tell ``recipients`` in the app that ``hold`` failed, with the target it was for."""
    _notify_staff(
        CARD_HOLD_FAILED_VERB,
        hold,
        recipients,
        lambda: _("The card hold for %(target)s failed.") % {"target": str(target)},
    )


def notify_partially_paid_in_app(
    hold: "AbstractCardHold", target: "Model", recipients: Iterable["AbstractBaseUser"]
) -> None:
    """Tell ``recipients`` in the app that the charge above ``hold`` was declined."""
    _notify_staff(
        CARD_HOLD_PARTIALLY_PAID_VERB,
        hold,
        recipients,
        lambda: (
            _("%(target)s was only partly paid: the charge above the hold was declined.")
            % {"target": str(target)}
        ),
    )
