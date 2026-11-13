"""What a hold attaches to: the target registry and the hooks a project implements.

A target is any model a hold can back (an order, a booking, a reservation). The project
registers an adapter per model in ``BASEAPP_PAYMENTS_CARD_HOLD_TARGETS``::

    BASEAPP_PAYMENTS_CARD_HOLD_TARGETS = {
        "orders.Order": "apps.orders.card_holds.OrderHoldTarget",
    }

Adapters usually subclass :class:`BaseHoldTarget`, which supplies the optional hooks.
Card holds never import the target's app; everything they need to know about a target
comes through these hooks.
"""

import datetime
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model, Q, QuerySet
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from .utils import Card


# --- Defaults (Constance, contributed by the plugin) -----------------------------------

DEFAULT_BUFFER_PERCENT = Decimal("10")
# Stripe honours an authorization for about 7 days when the customer is present, but a
# Visa authorization placed without them (merchant-initiated) lasts 5 days, and Stripe's
# exact window is 4 days 18 hours. A hold placed at the first sweep of D-4 (about 00:15)
# must then be captured by about 18:00 on D. A 5-day window would outlive it.
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 4
DEFAULT_WINDOW_DAYS = MAX_WINDOW_DAYS


class HoldAmountMode(str, enum.Enum):
    """What a target's hold covers, which every adapter that uses holds declares
    (``hold_amount_mode``): the value alone, or the value plus a buffer
    (``CARD_HOLDS_BUFFER_PERCENT``, or the adapter's ``buffer_percent()``)."""

    VALUE = "value"
    VALUE_PLUS_BUFFER = "value_plus_buffer"


def _constance(name: str, default: Any) -> Any:
    """A Constance value, or ``default`` when the project didn't merge the plugin's keys."""
    from constance import config

    try:
        value = getattr(config, name)
    except AttributeError:
        return default
    return default if value is None else value


def default_buffer_percent() -> Decimal:
    """``CARD_HOLDS_BUFFER_PERCENT``, never negative."""
    value = Decimal(str(_constance("CARD_HOLDS_BUFFER_PERCENT", DEFAULT_BUFFER_PERCENT)))
    return max(value, Decimal("0"))


def default_window_days() -> int:
    """``CARD_HOLDS_WINDOW_DAYS``, clamped to 1–4 days."""
    value = int(_constance("CARD_HOLDS_WINDOW_DAYS", DEFAULT_WINDOW_DAYS))
    return min(max(value, MIN_WINDOW_DAYS), MAX_WINDOW_DAYS)


def deferral_enabled() -> bool:
    """``CARD_HOLDS_DEFERRAL_ENABLED``: whether holds may be scheduled for later."""
    return bool(_constance("CARD_HOLDS_DEFERRAL_ENABLED", False))


def window_days_of(adapter: "HoldTarget") -> int:
    """``adapter.window_days()``, clamped to 1–4 days like the Constance value: an
    override can't outlive Stripe's off-session authorization either."""
    return min(max(int(adapter.window_days()), MIN_WINDOW_DAYS), MAX_WINDOW_DAYS)


@dataclass(frozen=True)
class HoldAmount:
    """What a target costs: the estimate, and its own buffer (``None``: the default)."""

    estimated_cents: int
    buffer_percent: Decimal | None = None


@runtime_checkable
class HoldTarget(Protocol):
    """The hooks card holds call on a target model. All run in the caller's transaction.

    Declarations, checked when the targets are registered (:func:`get_targets`):

    - ``uses_holds``: ``True`` to authorize the card ahead of the target's date (a hold,
      captured on the date), ``False`` to save the card only and charge it directly on the
      date through ``capture()``'s ``charge``. Required.
    - ``hold_amount_mode``: a :class:`HoldAmountMode`, what the hold covers: the value
      alone (``"value"``) or the value plus a buffer (``"value_plus_buffer"``). Required
      when ``uses_holds``.

    Placement:

    - ``owner(target)``: the user whose card backs the target. A hold is only linked to a
      target its own customer owns.
    - ``hold_amount(target, card)``: the target's price, re-read under the lock right
      before the hold is linked. ``target`` may be unsaved (the pre-authorization
      check); ``card`` is the card being held, for card-dependent prices.
    - ``lock(target_pk)``: ``SELECT ... FOR UPDATE`` the target and return it, or ``None``
      when it no longer exists. Always taken before the hold's own row lock.

    Release and the sweep:

    - ``filter_cancelled(qs)``: the targets whose hold must be released.
    - ``filter_card_released(qs)``: the targets that are done with the card (charged, or
      settled some other way), whose open hold is released unless a charge is in flight.
    - ``charge_may_be_in_flight(target)``: a charge of the target's card may still be
      running in Stripe, so its hold is left alone for now.

    Deferred placement (``CARD_HOLDS_DEFERRAL_ENABLED``):

    - ``target_date(target)``: the date the target is charged on. Only a target dated
      after today takes a hold (or has its card saved); ``None``, today or a past date
      answers ``charge_now`` and the project charges it directly. A deferred hold is
      placed ``window_days()`` before it.
    - ``filter_holdable(qs)``: the targets that may still get a hold; a scheduled hold
      is placed only while its target is among them.
    - ``cancel(target, actor)``: cancel a target whose hold failed and wasn't kept.
    - ``staff_recipients(target)``: who hears about a failed hold.
    - ``notify_hold_failed(target, hold)``: tell them; the default emails
      ``staff_recipients(target)``. Runs after the failure commits.
    - ``window_days()`` / ``buffer_percent()``: per-model defaults, Constance otherwise.
    """

    model: type[Model]
    uses_holds: bool
    hold_amount_mode: "HoldAmountMode | str"

    def owner(self, target: Model) -> "AbstractBaseUser":
        """The user whose card backs the target."""

    def hold_amount(self, target: Model, card: "Card | None" = None) -> HoldAmount:
        """The target's price; ``target`` may be unsaved."""

    def target_date(self, target: Model) -> datetime.date | None:
        """The date the target is for, or ``None``."""

    def lock(self, target_pk: Any) -> Model | None:
        """Lock the target's row (``SELECT ... FOR UPDATE``); ``None`` when it is gone."""

    def filter_holdable(self, queryset: QuerySet) -> QuerySet:
        """The targets that may still get a hold."""

    def filter_cancelled(self, queryset: QuerySet) -> QuerySet:
        """The targets whose hold must be released."""

    def filter_card_released(self, queryset: QuerySet) -> QuerySet:
        """The targets done with the card."""

    def charge_may_be_in_flight(self, target: Model) -> bool:
        """Whether a charge of the target's card may still be running."""

    def cancel(self, target: Model, actor: "AbstractBaseUser | None") -> None:
        """Cancel a target whose hold failed and wasn't kept."""

    def staff_recipients(self, target: Model) -> Iterable["AbstractBaseUser"]:
        """Who hears about a failed hold."""

    def notify_hold_failed(self, target: Model, hold: Any) -> None:
        """Tell staff a deferred hold failed (after the failure commits)."""

    def window_days(self) -> int:
        """Days before ``target_date`` to place the hold."""

    def buffer_percent(self) -> Decimal:
        """Percent added on top of the estimate."""


class BaseHoldTarget:
    """Defaults for every hook but ``owner``, ``hold_amount``, ``target_date`` and
    ``filter_cancelled``, which only the project can answer. ``uses_holds`` and (with
    holds) ``hold_amount_mode`` have no default either: a subclass declares them."""

    model: type[Model]

    def owner(self, target: Model) -> "AbstractBaseUser":
        raise NotImplementedError(f"{type(self).__name__} must implement owner()")

    def hold_amount(self, target: Model, card: "Card | None" = None) -> HoldAmount:
        raise NotImplementedError(f"{type(self).__name__} must implement hold_amount()")

    def target_date(self, target: Model) -> datetime.date | None:
        raise NotImplementedError(f"{type(self).__name__} must implement target_date()")

    def lock(self, target_pk: Any) -> Model | None:
        return self.model._default_manager.select_for_update().filter(pk=target_pk).first()

    def filter_holdable(self, queryset: QuerySet) -> QuerySet:
        return queryset

    def filter_cancelled(self, queryset: QuerySet) -> QuerySet:
        raise NotImplementedError(f"{type(self).__name__} must implement filter_cancelled()")

    def filter_card_released(self, queryset: QuerySet) -> QuerySet:
        return queryset.none()

    def charge_may_be_in_flight(self, target: Model) -> bool:
        return False

    def cancel(self, target: Model, actor: "AbstractBaseUser | None") -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement cancel()")

    def staff_recipients(self, target: Model) -> Iterable["AbstractBaseUser"]:
        """Active users who may decide a failed hold: granted ``change_cardhold`` (directly
        or through a group), or superusers. Staff status alone isn't enough."""
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from .models import get_card_hold_model

        perm = Permission.objects.filter(
            codename="change_cardhold",
            content_type=ContentType.objects.get_for_model(get_card_hold_model()),
        )
        return (
            get_user_model()
            ._default_manager.filter(is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(user_permissions__in=perm)
                | Q(groups__permissions__in=perm)
            )
            .distinct()
        )

    def notify_hold_failed(self, target: Model, hold: Any) -> None:
        from .emails import send_hold_failed_email

        send_hold_failed_email(hold, target, self.staff_recipients(target))

    def window_days(self) -> int:
        return default_window_days()

    def buffer_percent(self) -> Decimal:
        return default_buffer_percent()


_registry_cache: tuple[tuple, dict[type[Model], HoldTarget]] | None = None


def _setting() -> dict[str, str]:
    return dict(getattr(settings, "BASEAPP_PAYMENTS_CARD_HOLD_TARGETS", None) or {})


def get_targets() -> dict[type[Model], HoldTarget]:
    """Every registered target model and its adapter, built once per setting value."""
    global _registry_cache
    setting = _setting()
    key = tuple(sorted(setting.items()))
    if _registry_cache is not None and _registry_cache[0] == key:
        return _registry_cache[1]
    targets: dict[type[Model], HoldTarget] = {}
    for model_label, adapter_path in setting.items():
        try:
            model = apps.get_model(model_label)
        except (LookupError, ValueError) as error:
            raise ImproperlyConfigured(
                f"BASEAPP_PAYMENTS_CARD_HOLD_TARGETS: unknown model {model_label!r}"
            ) from error
        if model._meta.proxy:
            raise ImproperlyConfigured(
                f"BASEAPP_PAYMENTS_CARD_HOLD_TARGETS: {model_label!r} is a proxy model;"
                f" register its concrete model {model._meta.concrete_model._meta.label!r}"
            )
        adapter = import_string(adapter_path)()
        _check_declarations(adapter, model_label)
        if getattr(adapter, "model", None) is None:
            adapter.model = model
        targets[model] = adapter
    _registry_cache = (key, targets)
    return targets


def _check_declarations(adapter: Any, model_label: str) -> None:
    """Fail loudly on an adapter that doesn't say whether it uses holds, or (with holds)
    what the hold covers: neither has a silent default."""
    name = f"{type(adapter).__name__} ({model_label})"
    uses_holds = getattr(adapter, "uses_holds", None)
    if not isinstance(uses_holds, bool):
        raise ImproperlyConfigured(
            f"{name} must declare uses_holds = True (authorize ahead of the date) or"
            " False (save the card and charge it on the date)"
        )
    if not uses_holds:
        return
    mode = getattr(adapter, "hold_amount_mode", None)
    try:
        adapter.hold_amount_mode = HoldAmountMode(mode)
    except ValueError:
        raise ImproperlyConfigured(
            f"{name} must declare hold_amount_mode = {HoldAmountMode.VALUE.value!r} or"
            f" {HoldAmountMode.VALUE_PLUS_BUFFER.value!r}, not {mode!r}"
        ) from None


def target_for_model(model: type[Model]) -> HoldTarget:
    """The adapter of ``model`` (or of the concrete model a proxy stands for)."""
    targets = get_targets()
    concrete = model._meta.concrete_model
    adapter = targets.get(model) or targets.get(concrete)
    if adapter is None:
        raise ImproperlyConfigured(
            f"{model._meta.label} is not in BASEAPP_PAYMENTS_CARD_HOLD_TARGETS"
        )
    return adapter


def target_for_content_type_id(content_type_id: int) -> tuple[type[Model], HoldTarget] | None:
    """The registered model and adapter of a content type, or ``None``."""
    from django.contrib.contenttypes.models import ContentType

    model = ContentType.objects.get_for_id(content_type_id).model_class()
    if model is None:
        return None
    adapter = get_targets().get(model)
    return (model, adapter) if adapter is not None else None


def is_cancelled(adapter: HoldTarget, target_pk: Any) -> bool:
    return adapter.filter_cancelled(adapter.model._default_manager.filter(pk=target_pk)).exists()


def is_card_released(adapter: HoldTarget, target_pk: Any) -> bool:
    return adapter.filter_card_released(
        adapter.model._default_manager.filter(pk=target_pk)
    ).exists()
