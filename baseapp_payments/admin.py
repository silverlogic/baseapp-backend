from typing import Any

import swapper
from django.contrib import admin
from django.db.models import Model
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from .models import (
    NOT_PREFETCHED,
    card_holds_enabled,
    get_card_hold_model,
    prefetched_card_hold,
)

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("entity_id", "remote_customer_id")
    search_fields = ("entity_id", "remote_customer_id")
    readonly_fields = ("remote_customer_id",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_id",
        "remote_subscription_id",
    )
    search_fields = ("customer_id", "remote_subscription_id")
    readonly_fields = ("remote_subscription_id", "customer_id")


# Stripe's zero-decimal currencies: their amounts are whole units, not hundredths.
ZERO_DECIMAL_CURRENCIES = frozenset(
    "bif clp djf gnf jpy kmf krw mga pyg rwf ugx vnd vuv xaf xof xpf".split()
)


def _amount(minor_units: int | None, currency: str) -> str:
    """An amount in the hold's own currency, symbol-agnostic: ``1,234.56 EUR``."""
    code = (currency or "usd").lower()
    if code in ZERO_DECIMAL_CURRENCIES:
        return f"{minor_units or 0:,} {code.upper()}"
    return f"{(minor_units or 0) / 100:,.2f} {code.upper()}"


def card_hold_admin_summary(target: Model) -> str:
    """One line describing ``target``'s card hold, for the project's own target admin.

    One query per call, unless the target's hold was prefetched
    (``prefetch_related(CARD_HOLD_PREFETCH_PATH)``, i.e. ``"document__card_hold"``, in
    the admin's ``get_queryset``): then none, which a ``list_display`` column needs.
    """
    if target is None or getattr(target, "pk", None) is None:
        return str(_("No card hold"))
    hold = prefetched_card_hold(target)
    if hold is NOT_PREFETCHED:
        hold = get_card_hold_model().objects.for_target(target).first()
    if hold is None:
        return str(_("No card hold"))
    card = " ".join(part for part in (hold.card_brand.title(), hold.card_last4) if part)
    if hold.status == hold.Status.SAVED:
        amount = _("%(amount)s estimated") % {
            "amount": _amount(hold.estimated_amount_cents, hold.currency)
        }
    else:
        amount = _("%(amount)s held") % {"amount": _amount(hold.amount_cents, hold.currency)}
    parts = [card or str(_("Card")), amount, str(hold.get_status_display())]
    if hold.expires_at is not None:
        parts.append(
            _("expires %(when)s") % {"when": hold.expires_at.strftime("%Y-%m-%d %H:%M UTC")}
        )
    if hold.status == hold.Status.SCHEDULED and hold.hold_on is not None:
        parts.append(_("hold on %(day)s") % {"day": hold.hold_on.isoformat()})
    if hold.failure_code:
        parts.append(_("failure: %(code)s") % {"code": hold.failure_code})
    if hold.kept_at is not None:
        parts.append(_("kept"))
    return " · ".join(str(part) for part in parts)


class CardHoldAdmin(admin.ModelAdmin):
    """Read-only: holds change only through the card hold services and Stripe."""

    list_display = (
        "id",
        "customer",
        "status",
        "payment_status",
        "amount_cents",
        "card_brand",
        "card_last4",
        "hold_on",
        "kept",
        "failure_code",
        "expires_at",
        "created",
    )
    list_filter = ("status", "payment_status", "release_reason", "card_funding")
    search_fields = (
        "stripe_payment_intent_id",
        "stripe_setup_intent_id",
        "difference_payment_intent_id",
        "charge_payment_intent_id",
        "stripe_customer_id",
        "customer__email",
    )
    list_select_related = ("customer",)
    ordering = ("-created",)

    @admin.display(boolean=True, description=_("kept"))
    def kept(self, obj: Any) -> bool | None:
        """Staff kept the target of this failed hold; blank for any other hold."""
        if obj.status != obj.Status.FAILED and obj.kept_at is None:
            return None
        return obj.kept_at is not None

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


if card_holds_enabled():
    admin.site.register(get_card_hold_model(), CardHoldAdmin)
