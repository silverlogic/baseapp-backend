from graphene_django import DjangoObjectType
import graphene
from baseapp_devices.models import UserDevice
from graphene import relay


class UserDeviceType(DjangoObjectType):
    address = graphene.String()
    os_family = graphene.String()
    os_version = graphene.String()
    browser_family = graphene.String()
    browser_version = graphene.String()
    device_family = graphene.String()

    class Meta:
        model = UserDevice
        interfaces = (relay.Node,)
        fields = (
            "id",
            "user",
            "ip_address",
            "last_login",
            "created_at",
        )

    def resolve_address(self, info):
        if not self.location:
            return None
        return f"{self.location.get('city')}, {self.location.get('regionName')}, {self.location.get('country')}"

    def resolve_os_family(self, info):
        if not self.device_info:
            return None
        return self.device_info.get("os_family")

    def resolve_os_version(self, info):
        if not self.device_info:
            return None
        return ".".join([str(x) for x in self.device_info.get("os_version")])

    def resolve_browser_family(self, info):
        if not self.device_info:
            return None
        return self.device_info.get("browser_family")

    def resolve_browser_version(self, info):
        if not self.device_info:
            return None
        return ".".join([str(x) for x in self.device_info.get("browser_version")])

    def resolve_device_family(self, info):
        if not self.device_info:
            return None
        return self.device_info.get("device_family")
