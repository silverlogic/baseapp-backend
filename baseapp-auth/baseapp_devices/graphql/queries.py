import graphene

from baseapp_devices.graphql.object_types import UserDeviceType
from baseapp_devices.models import UserDevice


class UserDeviceQueries:
    all_user_devices = graphene.List(UserDeviceType)

    def resolve_all_user_devices(root, info):
        return UserDevice.objects.filter(user=info.context.user)
