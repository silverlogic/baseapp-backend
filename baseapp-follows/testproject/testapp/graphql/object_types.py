from baseapp_auth.graphql.object_types import UserObjectType as BaseUserObjectType

from baseapp_follows.graphql.object_types import FollowsInterface


class UserNode(BaseUserObjectType):
    class Meta(BaseUserObjectType.Meta):
        interfaces = BaseUserObjectType.Meta.interfaces + (FollowsInterface,)
