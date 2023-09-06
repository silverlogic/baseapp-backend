import factory
import swapper
from baseapp_auth.tests.factories import UserFactory

Notification = swapper.load_model("notifications", "Notification")


class AbstractNotificationFactory(factory.django.DjangoModelFactory):
    recipient = factory.SubFactory(UserFactory)

    class Meta:
        abstract = True


class NotificationFactory(AbstractNotificationFactory):
    actor = factory.SubFactory(UserFactory)

    class Meta:
        model = Notification
