import baseapp_auth.tests.helpers as h
import factory

UserFactory = h.get_user_factory()


class UserDeviceFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = "baseapp_devices.UserDevice"
