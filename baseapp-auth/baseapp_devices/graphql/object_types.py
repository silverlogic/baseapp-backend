from graphene_django import DjangoObjectType

from baseapp_devices.models import UserDevice


class UserDeviceType(DjangoObjectType):
    class Meta:
        model = UserDevice
        fields = (
            "id",
            "user",
            "ip_address",
            "device_info",
            "location",
            "last_login",
            "created_at",
        )
