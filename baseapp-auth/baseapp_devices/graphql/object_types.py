from graphene_django import DjangoObjectType

from baseapp_devices.models import UserDevice
from graphene import relay


class UserDeviceType(DjangoObjectType):
    class Meta:
        model = UserDevice
        interfaces = (relay.Node,)
        fields = (
            "id",
            "user",
            "ip_address",
            "device_info",
            "location",
            "last_login",
            "created_at",
        )
