"""Card hold emails: the default notice to staff when a deferred hold fails.

Adapters replace it by overriding ``notify_hold_failed`` (``hold_targets.BaseHoldTarget``);
the ``card_hold_failed`` signal is sent either way.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.core.mail import send_mail
from django.db.models import Model
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from baseapp_core.i18n import group_by_language

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from .models import AbstractCardHold


def _customer_name(user: Any) -> str:
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    email = getattr(user, "email", "") or ""
    if full_name and email:
        return f"{full_name} <{email}>"
    return full_name or email or str(user.pk)


def _render(hold: "AbstractCardHold", target: Model, target_date: Any) -> tuple[str, str]:
    """The subject and body, in the active language."""
    values = {
        "target": str(target),
        "customer": _customer_name(hold.customer),
        "date": target_date.isoformat() if target_date is not None else str(_("no date")),
        "reason": hold.failure_code or str(_("unknown")),
        "hold": hold.pk,
    }
    subject = _("Card hold failed for %(target)s") % values
    lines = [
        _("The card hold for %(target)s could not be placed.") % values,
        "",
        _("Customer: %(customer)s") % values,
        _("Date: %(date)s") % values,
        _("Reason: %(reason)s") % values,
        _("Card hold: #%(hold)s") % values,
        "",
        _(
            "The customer was not told. Keep it (the card is charged afresh when it"
            " closes) or cancel it."
        ),
    ]
    return str(subject), "\n".join(str(line) for line in lines)


def send_hold_failed_email(
    hold: "AbstractCardHold",
    target: Model,
    recipients: Iterable["AbstractBaseUser"],
) -> None:
    """Email ``recipients`` that ``hold`` failed: who the customer is, the target and its
    date. One email per language, each recipient reading it in their own."""
    from .hold_targets import target_for_model

    with_email = [user for user in recipients if getattr(user, "email", "")]
    if not with_email:
        return
    target_date = target_for_model(type(target)).target_date(target)
    for language, group in group_by_language(with_email).items():
        with translation.override(language):
            subject, message = _render(hold, target, target_date)
        send_mail(
            subject,
            message,
            from_email=None,
            recipient_list=[user.email for user in group],
        )
