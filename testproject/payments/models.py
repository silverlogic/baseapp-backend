from model_utils import FieldTracker

from baseapp_payments.models import (
    AbstractCardHold,
    BaseCustomer,
    BasePurchase,
    BasePurchaseLine,
    BaseSubscription,
)


class Customer(BaseCustomer):
    tracker = FieldTracker(["entity"])

    class Meta(BaseCustomer.Meta):
        pass


class Subscription(BaseSubscription):
    class Meta(BaseSubscription.Meta):
        pass


class Purchase(BasePurchase):
    class Meta(BasePurchase.Meta):
        pass


class PurchaseLine(BasePurchaseLine):
    class Meta(BasePurchaseLine.Meta):
        pass


class CardHold(AbstractCardHold):
    class Meta(AbstractCardHold.Meta):
        pass
