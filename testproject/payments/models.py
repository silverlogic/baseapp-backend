from model_utils import FieldTracker

from baseapp_payments.models import AbstractCardHold, BaseCustomer, BaseSubscription


class Customer(BaseCustomer):
    tracker = FieldTracker(["entity"])

    class Meta(BaseCustomer.Meta):
        pass


class Subscription(BaseSubscription):
    class Meta(BaseSubscription.Meta):
        pass


class CardHold(AbstractCardHold):
    class Meta(AbstractCardHold.Meta):
        pass
