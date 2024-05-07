from baseapp_auth.graphql.object_types import UserObjectType as BaseUserObjectType

from baseapp_blocks.graphql.object_types import BlocksInterface


class UserNode(BaseUserObjectType):
    class Meta(BaseUserObjectType.Meta):
        interfaces = BaseUserObjectType.Meta.interfaces + (BlocksInterface,)
