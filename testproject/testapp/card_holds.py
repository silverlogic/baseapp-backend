"""The card hold adapter of the test project's ``HoldableOrder``."""

import datetime
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet

from baseapp_payments.hold_targets import BaseHoldTarget, HoldAmount, HoldAmountMode

from .models import HoldableOrder


class HoldableOrderHoldTarget(BaseHoldTarget):
    model = HoldableOrder
    # Authorize ahead of the date, for the value plus the buffer. Tests that need the
    # other declarations patch these.
    uses_holds = True
    hold_amount_mode = HoldAmountMode.VALUE_PLUS_BUFFER
    # Tests set this to record the order in which locks are taken.
    lock_log: list[str] | None = None

    def owner(self, target: HoldableOrder) -> Any:
        return target.user

    def hold_amount(self, target: HoldableOrder, card: Any = None) -> HoldAmount:
        buffer = Decimal(target.buffer_percent) if target.buffer_percent is not None else None
        return HoldAmount(estimated_cents=target.amount_cents, buffer_percent=buffer)

    def target_date(self, target: HoldableOrder) -> datetime.date | None:
        return target.target_date

    def lock(self, target_pk: Any) -> HoldableOrder | None:
        if HoldableOrderHoldTarget.lock_log is not None:
            HoldableOrderHoldTarget.lock_log.append("target")
        return super().lock(target_pk)

    def filter_cancelled(self, queryset: QuerySet) -> QuerySet:
        return queryset.filter(status=HoldableOrder.Status.CANCELLED)

    def filter_card_released(self, queryset: QuerySet) -> QuerySet:
        return queryset.filter(status=HoldableOrder.Status.CHARGED)

    def charge_may_be_in_flight(self, target: HoldableOrder) -> bool:
        return target.charge_in_flight

    def cancel(self, target: HoldableOrder, actor: Any) -> None:
        target.status = HoldableOrder.Status.CANCELLED
        target.save(update_fields=["status"])
