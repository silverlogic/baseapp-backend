from baseapp_devices.graphql.object_types import UserDeviceType
from baseapp_devices.models import UserDevice
from graphene_django import DjangoConnectionField


class UserDeviceQueries:
    all_user_devices = DjangoConnectionField(UserDeviceType)

    def resolve_all_user_devices(root, info, **kwargs):
        return UserDevice.objects.filter(user=info.context.user)
