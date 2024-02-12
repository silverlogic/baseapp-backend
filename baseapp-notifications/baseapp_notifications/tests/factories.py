import factory
import swapper
from baseapp_auth.tests.helpers import get_user_factory

Notification = swapper.load_model("notifications", "Notification")
UserFactory = get_user_factory()


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
