import factory
import swapper

from baseapp_core.tests.factories import UserFactory

Notification = swapper.load_model("notifications", "Notification")


class AbstractNotificationFactory(factory.django.DjangoModelFactory):
    recipient = factory.SubFactory(UserFactory)

    class Meta:
        abstract = True


class NotificationFactory(AbstractNotificationFactory):
    actor = factory.SubFactory(UserFactory)

    class Meta:
        model = Notification


class NotificationSettingFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = swapper.load_model("baseapp_notifications", "NotificationSetting")
